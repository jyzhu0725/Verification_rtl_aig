#pragma once

#include <string>
#include <cassert>

#include <mockturtle/algorithms/lut_mapper.hpp>
#include <mockturtle/algorithms/collapse_mapped.hpp>
#include <mockturtle/io/write_bench.hpp>
#include <mockturtle/io/write_dimacs.hpp>
#include <mockturtle/networks/klut.hpp>
#include <mockturtle/views/depth_view.hpp>

#include <my_mapper/my_mapper_base/score.hpp>
#include <my_mapper/my_mapper/score.hpp>
#include <my_mapper/my_mapper_v2/score.hpp>
#include <my_mapper/my_mapper_option.hpp>

using namespace mockturtle;

template<class Ntk>
void lut_map_common(Ntk &mapped_aig, const Options &opts) {
  lut_map_params ps;
  ps.cut_enumeration_ps.cut_size = 4u;
  ps.cut_enumeration_ps.cut_limit = 8u;
  ps.recompute_cuts = true;
  ps.area_oriented_mapping = true;
  ps.cut_expansion = true;
  ps.check_used_limits = opts.check_used_limits;
  lut_map_stats st;

  switch (opts.mapper_type) {
    case 0:
      lut_map<Ntk, true, lut_custom_cost_base>(mapped_aig, ps, &st);
      break;
    case 1:
      lut_map<Ntk, true, lut_custom_cost>(mapped_aig, ps, &st);
      break;
    case 2:
      lut_map<Ntk, true, lut_custom_cost_v2>(mapped_aig, ps, &st);
      break;
    default:
      assert(0 && "Wrong mapper_type");
      break;
  }
  const auto klut = *collapse_mapped_network<klut_network>( mapped_aig );

  // Output
  depth_view<klut_network> klut_d{ klut };
  printf("Size %d, Depth: %d, Time: %.2f\n", klut.num_gates(), klut_d.depth(), to_seconds( st.time_total));

  if (!opts.output_bench.empty()) {
    write_bench(klut, opts.output_bench);
  }
  if (!opts.cnf_output.empty()) {
    write_dimacs(klut, opts.cnf_output);
  }

#ifdef TMX_DEBUG
  write_dot(mapped_aig, "aig.dot");
  write_dot(klut, "klut.dot");
#endif
}
