#pragma once

#include <string>
#include <cassert>
#include <iostream>

#include <my_mapper/my_mapper_v2/score.hpp>

struct Options {
  std::string input;
  std::string output_bench;      // output bench file
  std::string cnf_output;
  uint32_t mapper_type {1};      // {0, lut_custom_cost_base},  {1 : lut_custom_cost}  {2 : lut_custom_cost_v2}
  uint32_t check_used_limits {0};
  uint32_t extract_xor {0};     // 0:none, 1:base, 2:gauss
  bool extract_adder {false};
};

class OptionParser {
public:
    void parse(int argc, char **argv) {
        for (int i = 1; i < argc; ++i) {
            std::string arg = argv[i];
            if (arg == "--help" || arg == "-h") {
                show_help();
            }
    
            auto it = option_table.find(arg);
            if (it != option_table.end()) {
                it->second(i, argc, argv, arg);
            }
        }
    
        if (opts.input.empty()) {
            std::cout << "[option error] : no input FILE" << std::endl;
            exit(0);
        }
    }   
    
    const Options& get_options() {
        return opts;
    }
    
private:
    void option_error(const std::string& option) {
        std::cout << "[parse option error] : " << option << " (try --help)." << std::endl;
        exit(0);
    }

    void parse_option_with_arg(int &i, int argc, char** argv, const std::string &option, std::string &target) {
        if (i + 1 >= argc) {
            option_error(option);
        }
    
        target = argv[++i];
    }
    
    void parse_option_with_arg(int &i, int argc, char** argv, const std::string &option, uint32_t &target) {
        if (i + 1 >= argc) {
            option_error(option);
        }
    
        target = std::stoi(argv[++i]);
    }
    
    void parse_option_with_arg(int &i, int argc, char** argv, const std::string &option, bool &target) {
        target = true;
    }
    
    // used for parse option [--cost_coeff]
    void parse_option_cost_coeff(int &i, int argc, char** argv, const std::string &option) {
        if (i + COST_TYPES_NUM >= argc) {
            option_error(option);
        }
        int total_weight = 0;
        for (int idx = 0; idx < COST_TYPES_NUM; idx++) {
            const int cur_weight = std::stoi(argv[++i]);
            my_cost_types_weight[idx] = (float)cur_weight / 100.0;
            total_weight += cur_weight;
        }
        if (total_weight != 100) {
            option_error(option);
        }
    }

    void show_help() {
        std::cout << "Options:\n"
        << "  --help, -h                          Show this help message\n"
        << "  --input FILE                        Specify input file\n"
        << "  --output_bench FILE                 Specify output bench file\n"
        << "  --cnf_output FILE                   Specify cnf output file\n"
        << "  --mapper_type INT                   Mapper type [0:base][1:mapper] [2:mapper-coeff]\n"
        << "  --check_used_limits INT             Update best cut: check used limits\n"
        << "  --extract_adder                     Extract adder\n"
        << "  --extract_xor INT                   Extract xor [0:none, 1:base, 2:gauss]\n"
        << "  --cost_coeff INT[COST_TYPES_NUM]    Cost coefficient fo mapper_type = 2\n";
        exit(0);
    }

private:
    Options opts;

    // 定义 option 映射表
    using Handler = std::function<void(int&, int, char**, const std::string&)>;
    std::unordered_map<std::string, Handler> option_table = {      
        {"--input",             [&](int& i, int argc, char** argv, const std::string& arg) { parse_option_with_arg(i, argc, argv, arg, opts.input); }},
        {"--output_bench",      [&](int& i, int argc, char** argv, const std::string& arg) { parse_option_with_arg(i, argc, argv, arg, opts.output_bench); }},
        {"--cnf_output",        [&](int& i, int argc, char** argv, const std::string& arg) { parse_option_with_arg(i, argc, argv, arg, opts.cnf_output); }},
        {"--mapper_type",       [&](int& i, int argc, char** argv, const std::string& arg) { parse_option_with_arg(i, argc, argv, arg, opts.mapper_type); }},
        {"--check_used_limits", [&](int& i, int argc, char** argv, const std::string& arg) { parse_option_with_arg(i, argc, argv, arg, opts.check_used_limits); }},
        {"--extract_adder",     [&](int& i, int argc, char** argv, const std::string& arg) { parse_option_with_arg(i, argc, argv, arg, opts.extract_adder); }},
        {"--extract_xor",       [&](int& i, int argc, char** argv, const std::string& arg) { parse_option_with_arg(i, argc, argv, arg, opts.extract_xor); }},
        {"--cost_coeff",        [&](int& i, int argc, char** argv, const std::string& arg) { parse_option_cost_coeff(i, argc, argv, arg); }},
    };
};
