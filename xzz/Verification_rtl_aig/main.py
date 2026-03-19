import os
import sys
import argparse
import tempfile
import shutil
import re

from utils import utils

MY_MAPPER = './tools/mockturtle/build/my_mapper/my_mapper'


def baseline_solve(case_name, aig_path, config, args):
    cnf_path = os.path.join(config['log_path'], '{}.cnf'.format(case_name))
    aigtocnf_cmd = 'tools/aiger/aigtocnf {} {}'.format(aig_path, cnf_path)
    utils.run_command(aigtocnf_cmd)
    cmd_solve = 'tools/kissat/build/kissat {} --time={}'.format(cnf_path, args.timeout)
    solve_info, kissat_wall_time = utils.run_command(cmd_solve)

    if not args.save_temp_files:
        os.remove(cnf_path)

    return solve_info, kissat_wall_time


def solve(case_name, aig_path, config, args):
    trans_time = 0

    # Map
    bench_path = os.path.join(config['log_path'], '{}.bench'.format(case_name))
    map_cmd = '{} {} --input {} --output_bench {}'.format(MY_MAPPER, config['mapper_args'], aig_path, bench_path)
    map_out1, map_time = utils.run_command(map_cmd)
    trans_time += map_time

    tmp_aig_path = os.path.join(config['log_path'], '{}.aiger'.format(case_name))
    tmp_syned_aig_path = os.path.join(config['log_path'], '{}_syned.aiger'.format(case_name))
    syn_recipe = 'strash; rewrite -lz; balance; rewrite -lz; balance; rewrite -lz; balance; refactor -lz; balance; refactor -lz; balance; '
    abc_cmd = './tools/abc/abc -c "read_bench {}; {} write_aiger {};"'.format(bench_path, syn_recipe, tmp_aig_path)
    abc_out1, abc_time = utils.run_command(abc_cmd)
    trans_time += abc_time
    abc_cmd = './tools/abc/abc -c "source ./tools/abc/abc.rc; read_aiger {}; fraig; resyn2; write_aiger {};"'.format(tmp_aig_path, tmp_syned_aig_path)
    abc_out2, abc_time = utils.run_command(abc_cmd)
    trans_time += abc_time

    solve_info, kissat_wall_time = baseline_solve(case_name, tmp_syned_aig_path, config, args)

    if not args.save_temp_files:
        os.remove(bench_path)
        os.remove(tmp_aig_path)
        os.remove(tmp_syned_aig_path)

    return solve_info, trans_time, kissat_wall_time


def blif_to_aig(blif_path, output_aig_path):
    """Convert BLIF to AIG using ABC: read_blif; strash; write_aiger."""
    abc_cmd = './tools/abc/abc -c "read_blif {}; strash; write_aiger {};"'.format(blif_path, output_aig_path)
    stdout, elapsed_time = utils.run_command(abc_cmd)

    if not os.path.exists(output_aig_path):
        raise RuntimeError("BLIF to AIG conversion failed. ABC output: {}".format(stdout))

    return output_aig_path, elapsed_time


def miter_construction(aig1_path, aig2_path, output_miter_path):
    abc_cmd = './tools/abc/abc -c "read_aiger {}; read_aiger {}; miter; write_aiger {};"'.format(
        aig1_path, aig2_path, output_miter_path)
    stdout, elapsed_time = utils.run_command(abc_cmd)

    if not os.path.exists(output_miter_path):
        raise RuntimeError("Miter construction failed. ABC output: {}".format(stdout))

    return output_miter_path, elapsed_time


def run_abc_cec(aig1_path, aig2_path, timeout_sec, match_outputs_by_order=True):
    """
    Run ABC combinational equivalence checking:
    - cec file1 file2
    - -T: time limit for fraig+SAT (seconds), aligned with kissat --time
    - -n: match PIs/POs by order (two BLIFs may have different port names)
    """
    flags = '-T {}'.format(int(timeout_sec))
    if match_outputs_by_order:
        flags += ' -n'
    abc_cmd = './tools/abc/abc -c "cec {} {} {};"'.format(flags, aig1_path, aig2_path)
    stdout, wall_time = utils.run_command(abc_cmd)
    return stdout, wall_time


def parse_abc_cec_result(cec_stdout, wall_time_sec):
    """Parse ABC cec stdout to get equivalence result and Time = x.xx sec (CPU time).
    If Time is not printed, fall back to wall-clock time."""
    equivalence = "UNKNOWN"
    text = cec_stdout

    if re.search(r'Networks are NOT EQUIVALENT', text) or re.search(r'Networks are NOT equivalent', text):
        equivalence = "NOT EQUIVALENT"
    elif re.search(r'Networks are UNDECIDED', text):
        equivalence = "UNKNOWN"
    elif re.search(r'Networks are equivalent', text):
        equivalence = "EQUIVALENT"

    time_match = re.search(r'Time\s*=\s*([\d.]+)\s*sec', text)
    if time_match:
        solve_time = float(time_match.group(1))
        time_note = "cec_reported_cpu"
    else:
        solve_time = wall_time_sec
        time_note = "wall_clock_fallback"

    return equivalence, solve_time, time_note


def parse_kissat_result(solve_info):
    """Keep the original semantics: SAT -> NOT EQUIVALENT, UNSAT -> EQUIVALENT.
    The time is taken from Kissat's `process-time`."""
    equivalence = "UNKNOWN"
    if 's SATISFIABLE' in solve_info:
        equivalence = "NOT EQUIVALENT"
    elif 's UNSATISFIABLE' in solve_info:
        equivalence = "EQUIVALENT"

    solve_time = 0.0
    time_match = re.search(r'c process-time\s+:\s+([\d.]+)', solve_info)
    if time_match:
        solve_time = float(time_match.group(1))

    return equivalence, solve_time


def main():
    parser = argparse.ArgumentParser(
        description='Read two BLIF files, convert to AIG, and compare ABC cec with Mapper+Kissat.')
    parser.add_argument('--blif1', type=str, required=True, help='Path to the first BLIF file.')
    parser.add_argument('--blif2', type=str, required=True, help='Path to the second BLIF file.')
    parser.add_argument('--timeout', type=int, default=3600,
                        help='Time limit (seconds) used for both Kissat --time and ABC cec -T (default: 3600).')
    parser.add_argument('--save_temp_files', action='store_true', help='Keep temporary AIG/miter/CNF files.')
    parser.add_argument('--log_path', type=str, default='./logs', help='Directory for logs and temporary files.')
    parser.add_argument('--mapper_args', type=str,
                        default='--mapper_type 1 --check_used_limits 3 --extract_xor 1',
                        help='Arguments passed to my_mapper.')
    parser.add_argument(
        '--cec_match_by_name',
        action='store_true',
        help='Match PIs/POs by name in cec (by default, use -n to match by order, which is safer for independent BLIFs).')

    args = parser.parse_args()

    if not os.path.exists(args.blif1):
        print("Error: BLIF file does not exist: {}".format(args.blif1))
        sys.exit(1)

    if not os.path.exists(args.blif2):
        print("Error: BLIF file does not exist: {}".format(args.blif2))
        sys.exit(1)

    if args.log_path:
        log_path = args.log_path
        os.makedirs(log_path, exist_ok=True)
    else:
        log_path = tempfile.mkdtemp(prefix='equiv_check_')

    try:
        config = {
            'log_path': log_path,
            'mapper_args': args.mapper_args
        }

        case_name = 'miter'

        aig1_path = os.path.join(log_path, 'blif1.aig')
        aig2_path = os.path.join(log_path, 'blif2.aig')

        _, t_blif1 = blif_to_aig(args.blif1, aig1_path)
        _, t_blif2 = blif_to_aig(args.blif2, aig2_path)

        # 方法 1：ABC cec
        cec_stdout, cec_wall = run_abc_cec(
            aig1_path, aig2_path, args.timeout,
            match_outputs_by_order=not args.cec_match_by_name)
        cec_eq, cec_time, cec_time_src = parse_abc_cec_result(cec_stdout, cec_wall)

        # 方法 2：miter + 现有 solve（mapper + ABC 综合 + Kissat）
        miter_path = os.path.join(log_path, '{}.aig'.format(case_name))
        _, t_miter = miter_construction(aig1_path, aig2_path, miter_path)

        solve_info, trans_time, kissat_wall = solve(case_name, miter_path, config, args)
        kissat_eq, kissat_proc_time = parse_kissat_result(solve_info)

        # Only print the equivalence result and solving time for both methods.
        # Method 1: use the CEC-reported Time = ... sec when available.
        print("========== Method 1: ABC cec ==========")
        print("Equivalence: {}".format(cec_eq))
        print("Solve Time: {:.4f} s".format(cec_time))

        # Method 2: use Kissat `process-time` as the solving time.
        print("========== Method 2: Ours ==========")
        print("Equivalence: {}".format(kissat_eq))
        print("Solve Time: {:.4f} s".format(kissat_proc_time))

    except Exception as e:
        print("Error: {}".format(str(e)))
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        if not args.log_path and not args.save_temp_files:
            if os.path.exists(log_path):
                shutil.rmtree(log_path)


if __name__ == '__main__':
    main()
