import os
import sys
import argparse
import tempfile
import shutil
from pathlib import Path

from utils import utils
from main import (
    blif_to_aig,
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
        'blif_strash.aig',
        'blif_strash_resyn2.aig',
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


def _run_one(
    blif_file: Path,
    log_path: str,
    use_temp_root: bool,
    *,
    job_label: str,
    multi_jobs_under_user_log: bool,
    args,
    case_name: str,
):
    """Run the full flow for one BLIF and print results."""
    config = {
        'log_path': log_path,
        'mapper_args': args.mapper_args
    }
    blif_str = str(blif_file)

    aig_strash_path = os.path.join(log_path, 'blif_strash.aig')
    aig_resyn_path = os.path.join(log_path, 'blif_strash_resyn2.aig')

    _, _ = blif_to_aig(blif_str, aig_strash_path)
    _, _ = blif_to_resyn2_aig(blif_str, aig_resyn_path)

    cec_stdout, cec_wall = run_abc_cec(
        aig_strash_path, aig_resyn_path, args.timeout,
        match_outputs_by_order=not args.cec_match_by_name)
    cec_eq, cec_time, _ = parse_abc_cec_result(cec_stdout, cec_wall)

    miter_path = os.path.join(log_path, '{}.aig'.format(case_name))
    _, _ = miter_construction(aig_strash_path, aig_resyn_path, miter_path)

    solve_info, _trans_time, _kissat_wall, _abc_wall = solve(case_name, miter_path, config, args)
    kissat_eq, kissat_proc_time = parse_kissat_result(solve_info)

    print("========== {} ==========".format(job_label))
    print("========== Method 1: ABC cec ==========")
    print("Equivalence: {}".format(cec_eq))
    print("Solve Time: {:.4f} s".format(cec_time))

    print("========== Method 2: Ours ==========")
    print("Equivalence: {}".format(kissat_eq))
    print("Solve Time: {:.4f} s".format(kissat_proc_time))


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
        description='Read BLIF file(s): strash-only AIG vs strash+resyn2 AIG, then ABC cec vs miter+Kissat '
                    '(aligned with main.py). Pass a .blif file or a directory (recursive *.blif).')
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

        job_failed = False
        try:
            _run_one(
                blif_file,
                log_path,
                use_temp_root,
                job_label=job_label,
                multi_jobs_under_user_log=multi_jobs_under_user_log,
                args=args,
                case_name=case_name,
            )
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
            sys.exit(1)


if __name__ == '__main__':
    main()
