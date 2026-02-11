import os
import sys
import argparse
import tempfile
import shutil
from utils import utils

MY_MAPPER = './tools/mockturtle/build/my_mapper/my_mapper'

def baseline_solve(case_name, aig_path, config, args):
    cnf_path = os.path.join(config['log_path'], '{}.cnf'.format(case_name))
    aigtocnf_cmd = 'tools/aiger/aigtocnf {} {}'.format(aig_path, cnf_path)
    utils.run_command(aigtocnf_cmd)
    cmd_solve = 'tools/kissat/build/kissat {} --time={}'.format(cnf_path, args.timeout)
    solve_info, _ = utils.run_command(cmd_solve)

    if not args.save_temp_files:
        os.remove(cnf_path)

    return solve_info


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
    
    solve_info = baseline_solve(case_name, tmp_syned_aig_path, config, args)
    
    if not args.save_temp_files:
        # Remove 
        os.remove(bench_path)
        os.remove(tmp_aig_path)
        os.remove(tmp_syned_aig_path)
    
    return solve_info, trans_time

def rtl_to_aig(rtl_path, output_aig_path):
    abc_cmd = './tools/abc/abc -c "read_verilog {}; strash; write_aiger {};"'.format(rtl_path, output_aig_path)
    stdout, elapsed_time = utils.run_command(abc_cmd)
    
    if not os.path.exists(output_aig_path):
        raise RuntimeError("RTL to AIG conversion failed. ABC output: {}".format(stdout))
    
    return output_aig_path, elapsed_time

def miter_construction(aig1_path, aig2_path, output_miter_path):
    abc_cmd = './tools/abc/abc -c "read_aiger {}; read_aiger {}; miter; write_aiger {};"'.format(
        aig1_path, aig2_path, output_miter_path)
    stdout, elapsed_time = utils.run_command(abc_cmd)
    
    if not os.path.exists(output_miter_path):
        raise RuntimeError("Miter construction failed. ABC output: {}".format(stdout))
    
    return output_miter_path, elapsed_time

def main():
    parser = argparse.ArgumentParser(description='RTL and AIG equivalence checking script')
    parser.add_argument('--rtl_path', type=str, default='./data/rtl/adder.v', help='RTL file path')
    parser.add_argument('--aig_path', type=str, default='./data/aig/adder.aig', help='AIG file path')
    parser.add_argument('--timeout', type=int, default=3600, help='Solving timeout in seconds, default 3600')
    parser.add_argument('--save_temp_files', action='store_true', help='Save temporary files')
    parser.add_argument('--log_path', type=str, default='./logs', help='Log and temporary file path')
    parser.add_argument('--mapper_args', type=str, default='', help='Mapper arguments')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.rtl_path):
        print("Error: RTL file does not exist: {}".format(args.rtl_path))
        sys.exit(1)
    
    if not os.path.exists(args.aig_path):
        print("Error: AIG file does not exist: {}".format(args.aig_path))
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
        
        rtl_aig_path = os.path.join(log_path, 'rtl_converted.aig')
        rtl_aig_path, rtl_conv_time = rtl_to_aig(args.rtl_path, rtl_aig_path)
        
        miter_path = os.path.join(log_path, '{}.aig'.format(case_name))
        miter_path, miter_time = miter_construction(rtl_aig_path, args.aig_path, miter_path)
        
        solve_info, trans_time = solve(case_name, miter_path, config, args)
        
        import re
        equivalence = "UNKNOWN"
        solve_time = 0.0
        
        if 's SATISFIABLE' in solve_info:
            equivalence = "NOT EQUIVALENT"
        elif 's UNSATISFIABLE' in solve_info:
            equivalence = "EQUIVALENT"
        
        time_match = re.search(r'c process-time\s+:\s+([\d.]+)', solve_info)
        if time_match:
            solve_time = float(time_match.group(1))
        
        print("Equivalence: {}, Solve Time: {:.2f}s".format(equivalence, solve_time))
        
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