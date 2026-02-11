#pragma once

#include <kitty/dynamic_truth_table.hpp>
#include <mockturtle/algorithms/lut_mapper.hpp>
#include <my_mapper/my_mapper_base/cost/cost.hpp>

LUT_AREA_TYPE get_tt_score_base(kitty::dynamic_truth_table const& tt)
{
  switch (tt._num_vars) {
    case 2:
        return SCORE_LIST_FANIN2_BASE[tt._bits[0]];
    case 3:
        return SCORE_LIST_FANIN3_BASE[tt._bits[0]];
    case 4:
        return SCORE_LIST_FANIN4_BASE[tt._bits[0]];
    default:
        return 0;
  }
}

struct lut_custom_cost_base
{
  std::pair<LUT_AREA_TYPE, uint32_t> operator()( kitty::dynamic_truth_table const& tt ) const
  {
    const auto score = get_tt_score_base(tt);
    return {score, 1}; /* area, delay */
  }
};
