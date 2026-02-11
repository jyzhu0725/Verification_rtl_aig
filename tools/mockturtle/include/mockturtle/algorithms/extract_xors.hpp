/*!
  \file extract_xors.hpp
  \brief Extracts XOR gates in the network
  \author Generated based on extract_adders.hpp
*/

#include <algorithm>
#include <array>
#include <vector>

#include <fmt/format.h>
#include <kitty/dynamic_truth_table.hpp>
#include <kitty/static_truth_table.hpp>
#include <parallel_hashmap/phmap.h>

#include "../networks/block.hpp"
#include "../networks/storage.hpp"
#include "../utils/node_map.hpp"
#include "../utils/stopwatch.hpp"
#include "../views/choice_view.hpp"
#include "cut_enumeration.hpp"

namespace mockturtle
{

struct extract_xors_params
{
  extract_xors_params()
  {
    cut_enumeration_ps.cut_limit = 49;
    cut_enumeration_ps.minimize_truth_table = false;
  }

  /*! \brief Parameters for cut enumeration
   *
   * The default cut limit is 49. By default,
   * truth table minimization is not performed.
   */
  cut_enumeration_params cut_enumeration_ps{};

  /*! \brief Be verbose */
  bool verbose{ false };
  bool xor_gauss { false };
};

struct extract_xors_stats
{
  /*! \brief Computed cuts. */
  uint32_t cuts_total{ 0 };

  /*! \brief XOR2 gates count. */
  uint32_t xor2{ 0 };

  /*! \brief Mapped XOR2 gates. */
  uint32_t mapped_xor2{ 0 };

  /*! \brief Total runtime. */
  stopwatch<>::duration time_total{ 0 };

  void report() const
  {
    std::cout << fmt::format( "[i] Cuts = {}\t XOR2 = {}\n", cuts_total, xor2 );
    std::cout << fmt::format( "[i] Mapped XOR2 = {}\n", mapped_xor2 );
    std::cout << fmt::format( "[i] Total runtime = {:>5.2f} secs\n", to_seconds( time_total ) );
  }
};

namespace detail
{

struct double_hash
{
  uint64_t operator()( const std::array<uint32_t, 2>& p ) const
  {
    uint64_t seed = hash_block( p[0] );
    hash_combine( seed, hash_block( p[1] ) );
    return seed;
  }
};

struct cut_enumeration_xor_cut
{
  /* no additional data needed for XOR extraction */
};

template<class Ntk>
class extract_xors_impl
{
public:
  using network_cuts_t = fast_network_cuts<Ntk, 2, true, cut_enumeration_xor_cut>;
  using cut_t = typename network_cuts_t::cut_t;
  using leaves_hash_t = phmap::flat_hash_map<std::array<uint32_t, 2>, std::vector<uint64_t>, double_hash>;
  using block_map = node_map<signal<block_network>, Ntk>;

public:
  explicit extract_xors_impl( Ntk& ntk, extract_xors_params const& ps, extract_xors_stats& st )
      : ntk( ntk ),
        ps( ps ),
        st( st ),
        cuts( fast_cut_enumeration<Ntk, 2, true, cut_enumeration_xor_cut>( ntk, ps.cut_enumeration_ps ) ),
        cuts_classes(),
        xor_candidates(),
        node_match( ntk.size(), UINT32_MAX )
  {
    cuts_classes.reserve( 1000 );
  }

  block_network run()
  {
    stopwatch t( st.time_total );

    auto [res, old2new] = initialize_map_network();

    if (ps.xor_gauss) {
      xor_gauss();
      create_classes_with_xor_gauss();
    } else {
      create_classes();
    }
    
    match_xor_gates();
    map();
    topo_sort();
    finalize( res, old2new );

    return res;
  }
    
private:
  void create_classes()
  {
    st.cuts_total = cuts.total_cuts();

    ntk.foreach_gate( [&]( auto const& n ) {
      uint32_t cut_index = 0;
      for ( auto& cut : cuts.cuts( ntk.node_to_index( n ) ) )
      {
        if ( cut->size() != 2 )
        {
          ++cut_index;
          continue;
        }

        kitty::static_truth_table<2> tt = cuts.truth_table( *cut );

        /* check for xor2 */
        bool is_xor = false;
        for ( uint32_t func : xor2func )
        {
          if ( tt._bits == func )
          {
            ++st.xor2;
            is_xor = true;
            break;
          }
        }

        if ( !is_xor )
        {
          ++cut_index;
          continue;
        }

        uint64_t data = ( static_cast<uint64_t>( ntk.node_to_index( n ) ) << 16 ) | cut_index;
        std::array<uint32_t, 2> leaves = { 0, 0 };
        uint32_t i = 0;
        for ( auto l : *cut )
          leaves[i++] = l;

        /* sort leaves to ensure consistent ordering */
        if ( leaves[0] > leaves[1] )
          std::swap( leaves[0], leaves[1] );

        /* add to hash table */
        auto& v = cuts_classes[leaves];
        v.push_back( data );

        ++cut_index;
      }
    } );
  }

  void match_xor_gates()
  {
    xor_candidates.reserve( cuts_classes.size() );

    for ( auto& it : cuts_classes )
    {
      /* For XOR gates, we can have multiple equivalent implementations */
      for ( uint32_t i = 0; i < it.second.size(); ++i )
      {
        uint64_t data = it.second[i];
        xor_candidates.push_back( data );
      }
    }
  }

  void map()
  {
    selected.reserve( xor_candidates.size() );

    ntk.incr_trav_id();

    for ( uint32_t i = 0; i < xor_candidates.size(); ++i )
    {
      uint64_t data = xor_candidates[i];
      uint32_t node_index = data >> 16;

      /* check if node is already mapped */
      if ( node_match[node_index] != UINT32_MAX )
        continue;

      selected.push_back( i );
      node_match[node_index] = i;
      ++st.mapped_xor2;
    }
  }

  void topo_sort()
  {
    topo_order.reserve( ntk.size() );

    ntk.incr_trav_id();
    ntk.incr_trav_id();

    /* add constants and CIs */
    const auto c0 = ntk.get_node( ntk.get_constant( false ) );
    ntk.set_visited( c0, ntk.trav_id() );

    if ( const auto c1 = ntk.get_node( ntk.get_constant( true ) ); ntk.visited( c1 ) != ntk.trav_id() )
    {
      ntk.set_visited( c1, ntk.trav_id() );
    }

    ntk.foreach_ci( [&]( auto const& n ) {
      if ( ntk.visited( n ) != ntk.trav_id() )
      {
        ntk.set_visited( n, ntk.trav_id() );
      }
    } );

    /* sort topologically */
    ntk.foreach_co( [&]( auto const& f ) {
      if ( ntk.visited( ntk.get_node( f ) ) == ntk.trav_id() )
        return;
      topo_sort_rec( ntk.get_node( f ) );
    } );
  }

  bool is_xor_candidate( node<Ntk> const& n )
  {
    for (auto& data : xor_candidates)
    {
      uint32_t node_index = data >> 16;
      if (ntk.node_to_index(n) == node_index)
        return true;
    }
    return false;
  }

  void topo_sort_rec( node<Ntk> const& n )
  {
    /* is permanently marked? */
    if ( ntk.visited( n ) == ntk.trav_id() )
      return;

    if (is_xor_candidate(n))
    {
      ntk.set_visited( n, ntk.trav_id() - 1 );
      uint32_t node_index = ntk.node_to_index(n);
      auto& data = xor_candidates[node_match[node_index]];
      cut_t const& cut = cuts.cuts( data >> 16 )[data & UINT16_MAX];

      for ( auto l : cut )
      {
        topo_sort_rec( ntk.index_to_node(l) );
      }
      ntk.set_visited( n, ntk.trav_id() );
      topo_order.push_back( n );
    }
    else
    { 
      /* ensure that the node is not visited or temporarily marked */
      assert( ntk.visited( n ) != ntk.trav_id() );
      assert( ntk.visited( n ) != ntk.trav_id() - 1 );

      /* mark node temporarily */
      ntk.set_visited( n, ntk.trav_id() - 1 );

      /* mark cut leaves */
      ntk.foreach_fanin( n, [&]( auto const& f ) {
      topo_sort_rec( ntk.get_node( f ) );
      } );

      /* ensure that the node is not visited */
      assert( ntk.visited( n ) != ntk.trav_id() );

      /* mark node n permanently */
      ntk.set_visited( n, ntk.trav_id() );

      /* visit node */
      topo_order.push_back( n );
    }
  }

  std::pair<block_network, block_map> initialize_map_network()
  {
    block_network dest;
    block_map old2new( ntk );

    old2new[ntk.get_node( ntk.get_constant( false ) )] = dest.get_constant( false );
    if ( ntk.get_node( ntk.get_constant( true ) ) != ntk.get_node( ntk.get_constant( false ) ) )
      old2new[ntk.get_node( ntk.get_constant( true ) )] = dest.get_constant( true );

    ntk.foreach_ci( [&]( auto const& n ) {
      old2new[n] = dest.create_pi();
    } );
    return { dest, old2new };
  }

  void finalize( block_network& res, block_map& old2new )
  {
    for ( auto const& n : topo_order )
    {
      if ( ntk.is_pi( n ) || ntk.is_constant( n ) )
        continue;

      uint32_t node_index = ntk.node_to_index( n );
      if ( node_match[node_index] != UINT32_MAX )
      {
        /* This is a mapped XOR gate */
        finalize_xor_gate( res, old2new, n );
      }
      else
      {
        /* This is a regular gate */
        finalize_simple_gate( res, old2new, n );
      }
    }

    /* Create POs */
    ntk.foreach_co( [&]( auto const& f ) {
      res.create_po( ntk.is_complemented( f ) ? !old2new[f] : old2new[f] );
    } );
  }

  inline void finalize_simple_gate( block_network& res, block_map& old2new, node<Ntk> const& n )
  {
    std::vector<signal<block_network>> children;
    ntk.foreach_fanin( n, [&]( auto const& f ) {
      auto s = old2new[f] ^ ntk.is_complemented( f );
      children.push_back( s );
    } );

    /* Create a generic gate with the same function */
    old2new[n] = res.create_node( children, ntk.node_function( n ) );
  }

  inline void finalize_xor_gate( block_network& res, block_map& old2new, node<Ntk> const& n )
  {
    uint32_t node_index = ntk.node_to_index( n );
    uint32_t match_index = node_match[node_index];
    uint64_t data = xor_candidates[match_index];
    uint32_t cut_index = data & UINT16_MAX;

    /* Get the original cut */
    cut_t const& cut = cuts.cuts( node_index )[cut_index];
    kitty::static_truth_table<2> tt = cuts.truth_table( cut );

    /* Find the correct XOR function form and polarity */
    uint32_t func_index = 0;
    for ( uint32_t func : xor2func )
    {
      if ( tt._bits == func )
        break;
      ++func_index;
    }

    /* Create the XOR gate */
    std::array<signal<block_network>, 2> children;
    uint32_t i = 0;
    for ( auto l : cut )
    {
      children[i] = old2new[ntk.index_to_node( l )];
      ++i;
    }

    /* Create XOR2 gate */
    old2new[n] = (func_index == 0) ? res.create_xor( children[0], children[1] ) :
                                     res.create_xnor( children[0], children[1] );
  }

#pragma region XOR GAUSS
private:
  bool is_supported_xor(cut_t *cut) {
    const auto cut_size = cut->size();
    const auto truth_value = cuts.truth_table(*cut)._bits;
    auto it = supported_xor_types.find({cut_size, truth_value});
    return it != supported_xor_types.end();
  }

  void xor_cuts_collect() {
    ntk.foreach_gate( [&]( auto const& n ) {
      const auto index = ntk.node_to_index( n );
      const auto &node_cut_set = cuts.cuts(index);
      for (cut_t *cut : node_cut_set) {
        if (is_supported_xor(cut)) {
          xor_cuts[index] = cut;
          break;
        }
      }
    } );
  }

  void xor_cuts_group() {
    std::unordered_map<uint32_t, std::vector<uint32_t>> adj;
    for (const auto &[output , cut] : xor_cuts) {
      for (const auto input : *cut) {
        adj[input].push_back(output);
        adj[output].push_back(input);
      }
    }

    std::unordered_set<uint32_t> visited;
    for (const auto &[output, _] : xor_cuts) {
      if (visited.count(output)) {
          continue;
      }

      std::vector<uint32_t> group;
      std::queue<uint32_t> q;
      q.push(output);
      visited.insert(output);

      while (!q.empty()) {
        uint32_t node = q.front();
        q.pop();
        if (xor_cuts.count(node)) {
          group.push_back(node);
        }

        for (uint32_t nei : adj[node]) {
          if (!visited.count(nei)) {
            visited.insert(nei);
            q.push(nei);
          }
        }
      }
      if (group.size() > 1) {
        xor_groups.emplace_back(group);
      }
    }
  }

  uint32_t xor_cut_right_value (cut_t *cut) {
    const auto cut_size = cut->size();
    const auto truth_value = cuts.truth_table(*cut)._bits;
    auto it = supported_xor_types.find({cut_size, truth_value});
    if (it != supported_xor_types.end()) {
      if (it->second == XorType::Xor) return 0;
      if (it->second == XorType::Xnor) return 1;
    }

    assert (0 && "wrong cut size or truth_value");
  }

  void xor_group_to_matrix(const std::vector<uint32_t>& xor_group,
                           std::vector<std::set<uint32_t>> &rows,
                           std::vector<uint32_t>& rights) {
    rows.reserve(xor_group.size());
    rights.reserve(xor_group.size());

    std::set<uint32_t> row;
    uint32_t right;
    for (const auto& node : xor_group) {
      auto it = xor_cuts.find(node);
      assert (it != xor_cuts.end() && it->second);

      for (const auto leaf : *(it->second)) {
        row.insert(leaf);
      }
      row.insert(node);

      rows.emplace_back(row);
      row.clear();

      right = xor_cut_right_value(it->second);
      rights.emplace_back(right);
    }
  }

  void xor_group_gauss_debug(const std::vector<std::set<uint32_t>>& rows,
                             const std::vector<uint32_t>& rights,
                             std::ostream& fout = std::cout) {
    int n = rows.size();
    for (int i = 0; i < n; ++i) {
      const auto &row = rows[i];
      if (row.empty())
        continue;

      fout << "\tRow " << "[size=" << row.size() << " ]" << i << " : ";
      for (const auto v : row) {
        fout << v << " ";
      }
      fout << "| " << rights[i] << std::endl;
    }
  }

  void xor_group_to_dot(const std::vector<uint32_t>& xor_group, std::ostream& fout = std::cout) {
    fout << "digraph " << " {" << std::endl;
    fout << "\trankdir=LR;" << std::endl;
    for (const auto node : xor_group) {
      auto it = xor_cuts.find(node);
      assert (it != xor_cuts.end() && it->second);
      const auto right = xor_cut_right_value(it->second);

      for (const auto leaf : *(it->second)) {
        fout << "\t" << leaf << " -> " << node;
        if (right == 1) { // xnor
          fout << " [color=red]";
        }
        fout << ";" << std::endl;
      }
    }
    fout << "};" << std::endl;
  }

  void xor_group_gauss_result_analysis(const std::vector<std::set<uint32_t>> &rows_before,
                                       const std::vector<uint32_t> &rights_before,
                                       const std::vector<std::set<uint32_t>> &rows,
                                       const std::vector<uint32_t> &rights,
                                       const std::vector<uint32_t>& xor_group) {
    static int index = 0;
    bool used = false;
    for (const auto &row : rows) {
      bool row_used = false;
      const int size = row.size();

      if (size == 2) {
        row_used = true;
        for (const auto &value : row) {
          assert(xor_cuts.find(value) != xor_cuts.end());
          needed_xors.insert(value);
        }
      }
      used |= row_used;
    }

    if (ps.verbose && used) {
      std::string name = "xor_group_" + std::to_string(index) + ".txt";
      std::ofstream group_file(name);

      group_file << "Before gauss : " << std::endl;
      xor_group_gauss_debug(rows_before, rights_before, group_file);
      group_file << "After  gauss : " << std::endl;
      xor_group_gauss_debug(rows, rights, group_file);
      group_file << std::endl;

      xor_group_to_dot(xor_group, group_file);
      index++;
    }
  }

  void xor_group_gauss(const std::vector<uint32_t>& xor_group) {
    std::vector<std::set<uint32_t>> rows;
    std::vector<uint32_t> rights;
    xor_group_to_matrix (xor_group, rows, rights);

    auto rows_before = rows;
    auto rights_before = rights;

    // 收集所有变量编号，排序后依次消元
    std::set<uint32_t> all_vars;
    for (const auto& row : rows) {
      for (const auto &r : row) all_vars.insert(r);
    }
    std::vector<uint32_t> sorted_vars(all_vars.begin(), all_vars.end());

    int n = rows.size();
    int row = 0;
    for (int var : sorted_vars) {
      // 1. 找主元行
      int piv = -1;
      for (int i = row; i < n; ++i) {
        if (rows[i].count(var)) { piv = i; break; }
      }
      if (piv == -1) continue;

      // 2. 交换
      std::swap(rows[row], rows[piv]);
      std::swap(rights[row], rights[piv]);
      // 3. 消元
      for (int i = 0; i < n; ++i) {
        if (i == row || !rows[i].count(var)) {
          continue;
        }

        std::set<uint32_t> new_row;
        std::set_symmetric_difference(rows[i].begin(), rows[i].end(),
                                      rows[row].begin(), rows[row].end(),
                                      std::inserter(new_row, new_row.begin()));
        rows[i] = std::move(new_row);
        rights[i] ^= rights[row];
    }
      ++row;
    }

    xor_group_gauss_result_analysis(rows_before, rights_before, rows, rights, xor_group);
  }

  void xor_gauss() {
    // collect xor cuts
    xor_cuts_collect();
    // group xor cuts
    xor_cuts_group();

    // gauss
    for (const auto &xor_group : xor_groups) {
      assert (xor_group.size() > 1);
      xor_group_gauss(xor_group);
    }
  }

  // reference create_classes()
  void create_classes_with_xor_gauss() {
    st.cuts_total = cuts.total_cuts();

    ntk.foreach_gate( [&]( auto const& n ) {
      uint32_t cut_index = 0;
      const auto index = ntk.node_to_index( n );
      if (!needed_xors.count(index)) {
        return;
      }

      const auto it = xor_cuts.find(index);
      assert (it != xor_cuts.end());
      const auto target_cut = it->second;
      for ( auto& cut : cuts.cuts(index) ) {
        if (cut != target_cut) {
          ++cut_index;
          continue;
        }

        ++st.xor2;
        uint64_t data = ( static_cast<uint64_t>( ntk.node_to_index( n ) ) << 16 ) | cut_index;
        std::array<uint32_t, 2> leaves = { 0, 0 };
        uint32_t i = 0;
        for ( auto l : *cut )
          leaves[i++] = l;

        /* sort leaves to ensure consistent ordering */
        if ( leaves[0] > leaves[1] )
          std::swap( leaves[0], leaves[1] );

        /* add to hash table */
        auto& v = cuts_classes[leaves];
        v.push_back( data );

        ++cut_index;
      }
    } );
  }
#pragma endregion

private:
  Ntk& ntk;
  extract_xors_params const& ps;
  extract_xors_stats& st;

  network_cuts_t cuts;
  leaves_hash_t cuts_classes;
  std::vector<uint64_t> xor_candidates;
  std::vector<uint32_t> selected;
  std::vector<uint32_t> node_match;

  std::vector<node<Ntk>> topo_order;
  /* XOR2 truth table functions: XOR and XNOR */
  const std::array<uint32_t, 2> xor2func = { 0x6, 0x9 };  // XOR: 0110, XNOR: 1001

// used for xor gauss
private:
  enum class XorType {None, Xor, Xnor};
  using XorCutKey = std::pair<uint32_t, uint64_t>;
  std::map<XorCutKey, XorType> supported_xor_types = {
    {{2, 0x6}, XorType::Xor},       // 2-input xor
    {{2, 0x9}, XorType::Xnor},      // 2-input xnor
  };

  std::unordered_map<uint32_t, cut_t*> xor_cuts;                    // xor_cuts: output => cut
  std::vector<std::vector<uint32_t>> xor_groups;                    // xor groups
  std::unordered_set<uint32_t> needed_xors;                           // xor need kept
};

} /* namespace detail */

/*! \brief XOR extraction.
 *
 * This function extracts 2-input XOR gates from a network.
 * It returns a `block_network` with extracted XOR gates replaced
 * by dedicated XOR blocks.
 *
 * **Required network functions:**
 * - `size`
 * - `is_pi`
 * - `is_constant`
 * - `node_to_index`
 * - `index_to_node`
 * - `get_node`
 * - `foreach_co`
 * - `foreach_node`
 * - `foreach_gate`
 * - `foreach_ci`
 * - `foreach_fanin`
 * - `node_function`
 * - `is_complemented`
 * - `get_constant`
 * - `create_node`
 * - `create_pi`
 * - `create_po`
 * - `create_xor`
 *
 * \param ntk Network
 * \param ps Parameters
 * \param pst Stats
 *
 */
template<class Ntk>
block_network extract_xors( Ntk& ntk, extract_xors_params const& ps = {}, extract_xors_stats* pst = {} )
{
  static_assert( is_network_type_v<Ntk>, "Ntk is not a network type" );
  static_assert( has_size_v<Ntk>, "Ntk does not implement the size method" );
  static_assert( has_is_pi_v<Ntk>, "Ntk does not implement the is_pi method" );
  static_assert( has_is_constant_v<Ntk>, "Ntk does not implement the is_constant method" );
  static_assert( has_node_to_index_v<Ntk>, "Ntk does not implement the node_to_index method" );
  static_assert( has_index_to_node_v<Ntk>, "Ntk does not implement the index_to_node method" );
  static_assert( has_get_node_v<Ntk>, "Ntk does not implement the get_node method" );
  static_assert( has_foreach_node_v<Ntk>, "Ntk does not implement the foreach_node method" );
  static_assert( has_foreach_gate_v<Ntk>, "Ntk does not implement the foreach_gate method" );
  static_assert( has_foreach_co_v<Ntk>, "Ntk does not implement the foreach_co method" );

  extract_xors_stats st;

  detail::extract_xors_impl p( ntk, ps, st );
  block_network res = p.run();

  if ( ps.verbose )
    st.report();

  if ( pst )
    *pst = st;

  return res;
}

}; /* namespace mockturtle */