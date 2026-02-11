#pragma once

#include <kitty/dynamic_truth_table.hpp>
#include <mockturtle/algorithms/lut_mapper.hpp>
#include <my_mapper/my_mapper_v2/cost/cost.hpp>

#define COST_TYPES_NUM 7

#define MY_COST_METRICS \
    X(ENTROPY) \
    X(SENSITIVITY) \
    X(DETERMINACY) \
    X(MONOTONICITY) \
    X(BRANCH) \
    X(NUM) \
    X(CONFLICT)

const float *SCORE_LIST_FANIN2_TOTAL[COST_TYPES_NUM] = {
#define X(name) SCORE_LIST_FANIN2_##name,
    MY_COST_METRICS
#undef X 
};

const float *SCORE_LIST_FANIN3_TOTAL[COST_TYPES_NUM] = {
#define X(name) SCORE_LIST_FANIN3_##name,
    MY_COST_METRICS
#undef X 
};

const float *SCORE_LIST_FANIN4_TOTAL[COST_TYPES_NUM] = {
#define X(name) SCORE_LIST_FANIN3_##name,
    MY_COST_METRICS
#undef X 
};

// sum is 1.0
float my_cost_types_weight[COST_TYPES_NUM] = {0, 0, 0, 0, 1, 0, 0};

float get_tt_score_v2 (kitty::dynamic_truth_table const &tt) {
    float score = 0;
    
    switch (tt._num_vars) {
        case 2: {
            // For 2-input LUTs
            for (int i = 0; i < COST_TYPES_NUM; i++) {
                score += my_cost_types_weight[i] * SCORE_LIST_FANIN2_TOTAL[i][tt._bits[0]];
            }
            break;
        }
        case 3: {
            // For 3-input LUTs
            for (int i = 0; i < COST_TYPES_NUM; i++) {
                score += my_cost_types_weight[i] * SCORE_LIST_FANIN3_TOTAL[i][tt._bits[0]];
            }  
            break;
        }
        case 4: {
            // for 4-input LUTs
            for (int i = 0; i < COST_TYPES_NUM; i++) {
                score += my_cost_types_weight[i] * SCORE_LIST_FANIN3_TOTAL[i][tt._bits[0]];
            } 
            break;
        }
        default:
            break;
    }
    return score;
}

struct lut_custom_cost_v2
{
  std::pair<LUT_AREA_TYPE, uint32_t> operator()( kitty::dynamic_truth_table const& tt ) const {
    const auto score = get_tt_score_v2(tt);
    return {score, 1}; /* area, delay */
  }
};
