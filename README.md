# RTL and AIG Equivalence Checking

This project provides a tool for checking equivalence between RTL (Verilog) designs and AIG (And-Inverter Graph) files.

## Prerequisites

- Python 3.x
- GCC/G++ compiler
- CMake (version >= 3.8)
- Make

## Building Tools

Before using the equivalence checking script, you need to compile the four tools in the `tools` directory:

### 1. ABC

ABC is a system for sequential logic synthesis and formal verification.

```bash
cd tools/abc
make
```

The compiled binary `abc` should be in `tools/abc/` directory.

### 2. AIGER

AIGER is a format, library and set of utilities for And-Inverter Graphs.

```bash
cd tools/aiger
./configure.sh
make
```

The compiled utilities (including `aigtocnf`) should be in `tools/aiger/` directory.

### 3. Kissat

Kissat is a SAT solver used for solving the CNF formulas.

```bash
cd tools/kissat
./configure
make
```

The compiled binary `kissat` should be in `tools/kissat/build/` directory.

### 4. Mockturtle

Mockturtle is a logic synthesis library. We need to build the mapper tool.

**Important**: If you encounter CMake errors about path mismatches (e.g., "CMakeCache.txt directory is different"), clean the build directory first:

```bash
cd tools/mockturtle
rm -rf build  # Clean old build files if they exist
mkdir -p build
cd build
cmake ..
make my_mapper
```

The compiled binary `my_mapper` should be in `tools/mockturtle/build/my_mapper/` directory.

**Note**: If you cloned or moved this repository from another location, make sure to clean all build directories before compiling to avoid path-related CMake errors.

## Usage

After building all tools, you can use the main script to perform equivalence checking:

```bash
python main.py --rtl_path <rtl_file> --aig_path <aig_file>
```

### Arguments

- `--rtl_path`: Path to the RTL (Verilog) file (default: `./data/rtl/adder.v`)
- `--aig_path`: Path to the AIG file (default: `./data/aig/adder.aig`)
- `--timeout`: Solving timeout in seconds (default: 3600)
- `--save_temp_files`: Save temporary files for debugging
- `--log_path`: Path for log and temporary files (default: `./logs`)
- `--mapper_args`: Additional arguments for the mapper tool

### Example

```bash
python main.py --rtl_path ./data/rtl/adder.v --aig_path ./data/aig/adder.aig
```

### Output

The script will output the equivalence result and solving time:

```
Equivalence: EQUIVALENT, Solve Time: 0.15s
```

or

```
Equivalence: NOT EQUIVALENT, Solve Time: 0.23s
```



