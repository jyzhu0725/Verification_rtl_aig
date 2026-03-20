import csv
import os
import re
import sys
import random
import argparse
import tempfile
import shutil
from pathlib import Path

from utils import utils
from main import (
    solve,
    miter_construction,
    run_abc_cec,
    parse_abc_cec_result,
    parse_kissat_result,
)


def blif_to_resyn2_aig(blif_path, output_aig_path):
    """One BLIF: read_blif; strash; resyn2; write_aiger (resyn2 is an alias in abc.rc; source it first)."""
    abc_cmd = (
        './tools/abc/abc -c "source ./tools/abc/abc.rc; read_blif {}; strash; resyn2; write_aiger {};"'
    ).format(blif_path, output_aig_path)
    stdout, elapsed_time = utils.run_command(abc_cmd)

    if not os.path.exists(output_aig_path):
        raise RuntimeError("BLIF (strash+resyn2) to AIG failed. ABC output: {}".format(stdout))

    return output_aig_path, elapsed_time


def _remove_syn_artifacts(log_path, case_name):
    """Remove intermediate files this script creates under log_path (leave unrelated files alone)."""
    names = [
        'blif_strash_resyn2.aig',
        'blif_resyn2_tampered.aig',
        'blif_resyn2_tamper_tmp.aag',
        'blif_resyn2_tamper_perturbed.aag',
        '{}.aig'.format(case_name),
        '{}.bench'.format(case_name),
        '{}.aiger'.format(case_name),
        '{}_syned.aiger'.format(case_name),
        '{}.cnf'.format(case_name),
    ]
    for name in names:
        p = os.path.join(log_path, name)
        if os.path.isfile(p):
            try:
                os.remove(p)
            except OSError:
                pass


def _collect_blif_files(input_path: Path):
    """If input is a .blif file, return a one-element list; if a directory, collect all .blif recursively."""
    input_path = input_path.resolve()
    if not input_path.exists():
        return None, None, "Path does not exist: {}".format(input_path)

    if input_path.is_file():
        if input_path.suffix.lower() != '.blif':
            return None, None, "Not a BLIF file: {}".format(input_path)
        return [input_path], input_path.parent, None

    if input_path.is_dir():
        found = sorted(input_path.rglob('*.blif'))
        return found, input_path, None

    return None, None, "Invalid path: {}".format(input_path)


def _work_subdir_slug(blif_file: Path, scan_root: Path) -> str:
    """Per-job subdirectory name under log_path in batch mode (avoids name clashes)."""
    rel = blif_file.resolve().relative_to(scan_root.resolve())
    return str(rel.with_suffix('')).replace(os.sep, '__')


def _blif_strash_and_gates_via_abc(blif_path: str) -> int:
    """Match interactive: read_blif; strash; print_stats — parse the `and = N` field from stdout."""
    abc_cmd = './tools/abc/abc -c "read_blif {}; strash; print_stats;"'.format(blif_path)
    stdout, _elapsed = utils.run_command(abc_cmd)
    m = re.search(r'\band\s*=\s*(\d+)', stdout)
    if not m:
        return -1
    return int(m.group(1))


def _tamper_resyn2_aig_via_aag(syn_aig_path: str, work_dir: str) -> str:
    """
    Same idea as create_sat.create_modified_aig: AIG -> AAG, flip one AND line's two fanin literals
    by +/-1 (within [2, M]), then AAG -> AIG. Intended to break functional equivalence vs the clean net.
    """
    tmp_aag = os.path.join(work_dir, 'blif_resyn2_tamper_tmp.aag')
    out_aag = os.path.join(work_dir, 'blif_resyn2_tamper_perturbed.aag')
    out_aig = os.path.join(work_dir, 'blif_resyn2_tampered.aig')

    cmd_in = './tools/aiger/aigtoaig {} {}'.format(syn_aig_path, tmp_aag)
    utils.run_command(cmd_in)
    if not os.path.isfile(tmp_aag) or os.path.getsize(tmp_aag) == 0:
        raise RuntimeError('Tamper: failed AIG->AAG (is tools/aiger/aigtoaig built?) {}'.format(tmp_aag))

    with open(tmp_aag, 'r') as f:
        lines = f.readlines()
    if not lines or not lines[0].strip().startswith('aag'):
        raise RuntimeError('Tamper: invalid AAG header')
    hdr = lines[0].strip().split()
    if len(hdr) < 6:
        raise RuntimeError('Tamper: bad AAG header line')
    M = int(hdr[1])
    I = int(hdr[2])
    L = int(hdr[3])
    O = int(hdr[4])
    A = int(hdr[5])
    if A == 0:
        print('Warning: no AND gates in resyn2 AIG; cannot tamper, using clean net as both sides.')
        return syn_aig_path

    modified = list(lines)
    and_start = I + L + O + 1
    if and_start >= len(modified):
        print('Warning: AAG too short for AND section; skipping tamper.')
        return syn_aig_path

    and_line_idx = random.randint(and_start, min(and_start + A - 1, len(modified) - 1))
    and_line = modified[and_line_idx].strip()
    if not and_line or ' ' not in and_line:
        print('Warning: bad AND line {}; skipping tamper.'.format(and_line_idx))
        return syn_aig_path
    parts = and_line.split()
    if len(parts) < 3:
        print('Warning: AND line has too few tokens; skipping tamper.')
        return syn_aig_path

    o1, o2 = int(parts[1]), int(parts[2])
    n1, n2 = o1, o2
    if o1 % 2 == 0:
        n1 = o1 + 1 if o1 + 1 <= M else o1 - 1
    else:
        n1 = o1 - 1 if o1 - 1 >= 2 else o1 + 1
    if o2 % 2 == 0:
        n2 = o2 + 1 if o2 + 1 <= M else o2 - 1
    else:
        n2 = o2 - 1 if o2 - 1 >= 2 else o2 + 1
    n1 = max(2, min(n1, M))
    n2 = max(2, min(n2, M))
    parts[1], parts[2] = str(n1), str(n2)
    modified[and_line_idx] = ' '.join(parts) + '\n'
    print('Tamper AND line {}: ({},{}) -> ({},{})'.format(and_line_idx, o1, o2, n1, n2))

    with open(out_aag, 'w') as f:
        f.writelines(modified)

    cmd_out = './tools/aiger/aigtoaig {} {}'.format(out_aag, out_aig)
    utils.run_command(cmd_out)
    if not os.path.isfile(out_aig) or os.path.getsize(out_aig) == 0:
        raise RuntimeError('Tamper: AAG->AIG failed {}'.format(out_aig))
    return out_aig


CSV_FIELDNAMES = [
    'blif_file',
    'num_gates',
    'abc_cec_result',
    'abc_cec_time_sec',
    'ours_result',
    'ours_solve_time_sec',
]


def _write_results_csv(csv_path: str, rows: list) -> None:
    """Write one summary CSV in English (overwrites existing file)."""
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES, extrasaction='ignore')
        w.writeheader()
        for row in rows:
            w.writerow(row)


def _run_one(
    blif_file: Path,
    log_path: str,
    use_temp_root: bool,
    *,
    job_label: str,
    multi_jobs_under_user_log: bool,
    args,
    case_name: str,
    blif_display: str,
):
    """Run the full flow for one BLIF, print results, return one CSV row dict.

    Pipeline (create_sat-style): BLIF -> resyn2 AIG (clean) -> tampered copy of that AIG;
    then ABC cec and Ours on clean vs tampered (expect NOT EQUIVALENT when tamper applies).
    """
    config = {
        'log_path': log_path,
        'mapper_args': args.mapper_args
    }
    blif_str = str(blif_file)
    and_gates = _blif_strash_and_gates_via_abc(blif_str)

    aig_resyn_path = os.path.join(log_path, 'blif_strash_resyn2.aig')
    _, _ = blif_to_resyn2_aig(blif_str, aig_resyn_path)
    aig_tampered_path = _tamper_resyn2_aig_via_aag(aig_resyn_path, log_path)

    cec_stdout, cec_wall = run_abc_cec(
        aig_resyn_path, aig_tampered_path, args.timeout,
        match_outputs_by_order=not args.cec_match_by_name)
    cec_eq, cec_time, _ = parse_abc_cec_result(cec_stdout, cec_wall)

    miter_path = os.path.join(log_path, '{}.aig'.format(case_name))
    _, _ = miter_construction(aig_resyn_path, aig_tampered_path, miter_path)

    solve_info, trans_time, _kissat_wall, _abc_wall = solve(case_name, miter_path, config, args)
    kissat_eq, kissat_proc_time = parse_kissat_result(solve_info)
    ours_solve_time = trans_time + kissat_proc_time

    print("========== {} ==========".format(job_label))
    print("========== Method 1: ABC cec (resyn2 vs tampered) ==========")
    print("Equivalence: {}".format(cec_eq))
    print("Solve Time: {:.4f} s".format(cec_time))

    print("========== Method 2: Ours ==========")
    print("Equivalence: {}".format(kissat_eq))
    print("Solve Time: {:.4f} s".format(ours_solve_time))

    return {
        'blif_file': blif_display,
        'num_gates': and_gates,
        'abc_cec_result': cec_eq,
        'abc_cec_time_sec': round(cec_time, 6),
        'ours_result': kissat_eq,
        'ours_solve_time_sec': round(ours_solve_time, 6),
    }


def _cleanup_job(
    log_path: str,
    use_temp_root: bool,
    multi_jobs_under_user_log: bool,
    save_temp_files: bool,
    case_name: str,
):
    if save_temp_files:
        if use_temp_root:
            print("Temp workdir kept: {}".format(log_path))
        return
    if use_temp_root:
        shutil.rmtree(log_path, ignore_errors=True)
    elif multi_jobs_under_user_log:
        shutil.rmtree(log_path, ignore_errors=True)
    else:
        _remove_syn_artifacts(log_path, case_name)


def main():
    parser = argparse.ArgumentParser(
        description='Read BLIF file(s): build resyn2-synthesized AIG, tamper it (create_sat-style AAG '
                    'AND fanin edit), then ABC cec vs miter+Kissat on clean vs tampered. '
                    'Pass a .blif file or a directory (recursive *.blif). Requires tools/aiger/aigtoaig.')
    parser.add_argument(
        '--blif',
        type=str,
        required=True,
        help='Path to one .blif file, or a directory (all .blif files under it recursively).')
    parser.add_argument('--timeout', type=int, default=3600,
                        help='Time limit (seconds) for ABC cec -T and Kissat --time (default: 3600).')
    parser.add_argument('--save_temp_files', action='store_true',
                        help='Keep work directory and all intermediate AIG/miter/CNF files.')
    parser.add_argument('--log_path', type=str, default=None,
                        help='Work directory. Default: system temp folder removed after each job '
                             '(unless --save_temp_files). If set: single job uses it directly; '
                             'multiple jobs use subdirs under it unless each job uses its own temp.')
    parser.add_argument('--mapper_args', type=str,
                        default='--mapper_type 1 --check_used_limits 3 --extract_xor 1',
                        help='Arguments passed to my_mapper.')
    parser.add_argument(
        '--cec_match_by_name',
        action='store_true',
        help='Match PIs/POs by name in cec (by default, use -n to match by order).')
    parser.add_argument(
        '--csv',
        type=str,
        default='syn_unequiv_summary.csv',
        metavar='FILE',
        help='Write per-case summary to this CSV (English headers). Use none to disable.',
    )

    args = parser.parse_args()
    case_name = 'miter'

    blif_list, scan_root, err = _collect_blif_files(Path(args.blif))
    if err:
        print("Error: {}".format(err))
        sys.exit(1)
    if not blif_list:
        print("No .blif files found under: {}".format(args.blif))
        sys.exit(1)

    n_jobs = len(blif_list)
    user_base = args.log_path
    if user_base:
        os.makedirs(user_base, exist_ok=True)

    csv_path = None
    if args.csv and args.csv.strip().lower() not in ('none', '-'):
        csv_path = os.path.abspath(args.csv)

    result_rows = []

    for idx, blif_file in enumerate(blif_list):
        rel_display = blif_file
        try:
            rel_display = blif_file.resolve().relative_to(scan_root.resolve())
        except ValueError:
            rel_display = blif_file.name

        if user_base is None:
            log_path = tempfile.mkdtemp(prefix='syn_equiv_')
            use_temp_root = True
            multi_jobs_under_user_log = False
        else:
            use_temp_root = False
            if n_jobs > 1:
                slug = _work_subdir_slug(blif_file, scan_root)
                log_path = os.path.join(user_base, slug)
                os.makedirs(log_path, exist_ok=True)
                multi_jobs_under_user_log = True
            else:
                log_path = user_base
                multi_jobs_under_user_log = False

        job_label = "FILE {} / {}: {}".format(idx + 1, n_jobs, rel_display)
        blif_display = str(rel_display)

        job_failed = False
        try:
            row = _run_one(
                blif_file,
                log_path,
                use_temp_root,
                job_label=job_label,
                multi_jobs_under_user_log=multi_jobs_under_user_log,
                args=args,
                case_name=case_name,
                blif_display=blif_display,
            )
            result_rows.append(row)
        except Exception as e:
            print("Error [{}]: {}".format(rel_display, str(e)))
            import traceback
            traceback.print_exc()
            job_failed = True
        finally:
            _cleanup_job(
                log_path, use_temp_root, multi_jobs_under_user_log,
                args.save_temp_files, case_name,
            )
        if job_failed:
            if csv_path and result_rows:
                _write_results_csv(csv_path, result_rows)
                print("Partial CSV written to {} ({} row(s)).".format(csv_path, len(result_rows)))
            sys.exit(1)

    if csv_path:
        _write_results_csv(csv_path, result_rows)
        print("Summary CSV written to {} ({} row(s)).".format(csv_path, len(result_rows)))


if __name__ == '__main__':
    main()
