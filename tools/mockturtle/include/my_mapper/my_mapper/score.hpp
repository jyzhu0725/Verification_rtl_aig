#pragma once

#include <kitty/dynamic_truth_table.hpp>
#include <mockturtle/algorithms/lut_mapper.hpp>
#include "my_mapper/my_mapper/cost/cost.hpp"

float get_tt_score(kitty::dynamic_truth_table const& tt)
{
  switch (tt._num_vars) {
    case 2:
      return SCORE_LIST_FANIN2[tt._bits[0]];
    case 3:
      return SCORE_LIST_FANIN3[tt._bits[0]];
    case 4:
      return SCORE_LIST_FANIN4[tt._bits[0]];
    default:
      return 0;
  }
}

struct lut_custom_cost
{
  std::pair<LUT_AREA_TYPE, uint32_t> operator()( kitty::dynamic_truth_table const& tt ) const
  {
    const auto score = get_tt_score(tt);
    return {score, 1}; /* area, delay */
  }
};
