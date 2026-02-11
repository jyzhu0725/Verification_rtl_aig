#include <lorina/aiger.hpp>
#include <mockturtle/mockturtle.hpp>
#include <../test/catch2/catch.hpp>

#include <string>
#include <vector>

#include <fmt/format.h>
#include <lorina/aiger.hpp>
#include <mockturtle/algorithms/experimental/decompose_multioutput.hpp>
#include <mockturtle/algorithms/aig_balancing.hpp>
#include <mockturtle/algorithms/extract_adders.hpp>
#include <mockturtle/algorithms/extract_xors.hpp>
#include <mockturtle/io/aiger_reader.hpp>
#include <mockturtle/networks/aig.hpp>
#include <mockturtle/networks/block.hpp>

#include <../experiments/experiments.hpp>

#include <my_mapper/my_mapper.hpp>


int main(int argc, char **argv)
{
  OptionParser parser;
  parser.parse(argc, argv);
  const Options& opts = parser.get_options();

  aig_network aig;
  auto const result = lorina::read_aiger(opts.input, aiger_reader(aig) );

  if ( result != lorina::return_code::success ){
      std::cout << "Read benchmark failed\n";
      return -1;
  }

  if (opts.extract_xor) {
    extract_xors_params params;
    params.xor_gauss = (opts.extract_xor == 2);
    params.verbose = true;
    block_network res = extract_xors(aig, params);
    mapping_view<block_network, true> mapped_aig{res};
    lut_map_common<decltype( mapped_aig )>(mapped_aig, opts);
  } else if (opts.extract_adder) {
    extract_adders_params aps;
    extract_adders_stats ast;
    block_network res = extract_adders( aig, aps, &ast );
    res = decompose_multioutput<block_network, block_network>(res);
    mapping_view<block_network, true> mapped_aig{res};

    lut_map_common<decltype( mapped_aig )>(mapped_aig, opts);
  } else {
    mapping_view<aig_network, true> mapped_aig{aig};

    lut_map_common<decltype( mapped_aig )>(mapped_aig, opts);
  }

  return 0;
}
