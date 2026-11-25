import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


def build_causal_graphs():
    """Constructs NetworkX DiGraphs for both Total Effect and Mediation models."""
    
    # ---------------------------------------------------------
    # 1. DAG A: Total Effect & Moderation Model (ATE / CATE)
    # ---------------------------------------------------------
    G_total = nx.DiGraph()
    nodes_total = {
        'task_evolution': ('treatment', (0.10, 0.80)),
        'reflection_evolution': ('treatment', (0.10, 0.55)),
        'tool_evolution': ('treatment', (0.10, 0.30)),
        'model': ('covariate', (0.50, 0.90)),
        'instance': ('covariate', (0.40, 0.12)),
        'difficulty': ('covariate', (0.65, 0.12)),
        'resolved': ('outcome', (0.90, 0.55))
    }
    for node, (role, pos) in nodes_total.items():
        G_total.add_node(node, role=role, pos=pos)

    edges_total = [
        ('task_evolution', 'resolved'),
        ('reflection_evolution', 'resolved'),
        ('tool_evolution', 'resolved'),
        ('model', 'resolved'),
        ('instance', 'difficulty'),
        ('difficulty', 'resolved')
    ]
    G_total.add_edges_from(edges_total)

    # ---------------------------------------------------------
    # 2. DAG B: Structural Mechanism & Mediation Model
    # ---------------------------------------------------------
    G_med = nx.DiGraph()
    nodes_med = {
        # Treatments
        'task_evolution': ('treatment', (0.08, 0.80)),
        'reflection_evolution': ('treatment', (0.08, 0.52)),
        'tool_evolution': ('treatment', (0.08, 0.24)),
        
        # Primary Mediators (Evolution Actions)
        'n_task_description_edits': ('mediator1', (0.36, 0.80)),
        'n_reflection_prompt_edits': ('mediator1', (0.36, 0.52)),
        'n_tools_created': ('mediator1', (0.36, 0.24)),
        
        # Secondary Mediators (Execution & Compute)
        'n_custom_tool_uses': ('mediator2', (0.64, 0.24)),
        'api_calls': ('mediator2', (0.64, 0.52)),
        'total_tokens': ('mediator2', (0.64, 0.80)),
        
        # Pre-treatment Covariates / Moderators
        'model': ('covariate', (0.50, 0.96)),
        'instance': ('covariate', (0.28, 0.04)),
        'difficulty': ('covariate', (0.58, 0.04)),
        
        # Outcome
        'resolved': ('outcome', (0.92, 0.52))
    }
    for node, (role, pos) in nodes_med.items():
        G_med.add_node(node, role=role, pos=pos)

    edges_med = [
        # Treatment -> Primary Mediators
        ('task_evolution', 'n_task_description_edits'),
        ('reflection_evolution', 'n_reflection_prompt_edits'),
        ('reflection_evolution', 'n_task_description_edits'),  # Cross-feature interaction
        ('tool_evolution', 'n_tools_created'),
        
        # Primary -> Secondary Mediators
        ('n_task_description_edits', 'api_calls'),
        ('n_reflection_prompt_edits', 'api_calls'),
        ('n_tools_created', 'n_custom_tool_uses'),
        ('n_tools_created', 'api_calls'),
        ('n_custom_tool_uses', 'api_calls'),
        
        # Secondary Mediators -> Trajectory & Outcome
        ('api_calls', 'total_tokens'),
        ('api_calls', 'resolved'),
        ('total_tokens', 'resolved'),
        ('n_custom_tool_uses', 'resolved'),
        ('n_task_description_edits', 'resolved'),
        ('n_reflection_prompt_edits', 'resolved'),
        
        # Direct Treatment -> Outcome (unmediated prompt/framing effects)
        ('task_evolution', 'resolved'),
        ('reflection_evolution', 'resolved'),
        ('tool_evolution', 'resolved'),
        
        # Pre-treatment Covariates -> Mediators & Outcome
        ('instance', 'difficulty'),
        ('model', 'resolved'),
        ('model', 'api_calls'),
        ('model', 'n_tools_created'),
        ('difficulty', 'resolved'),
        ('difficulty', 'api_calls'),
        ('model', 'n_task_description_edits'),
        ('model', 'n_reflection_prompt_edits'),
        ('model', 'n_tools_created'),
        ('difficulty', 'n_task_description_edits'),
        ('difficulty', 'n_reflection_prompt_edits'),
        ('difficulty', 'n_tools_created'),
        
    ]
    G_med.add_edges_from(edges_med)

    # Verify both graphs are valid Directed Acyclic Graphs
    assert nx.is_directed_acyclic_graph(G_total), "DAG A contains a cycle!"
    assert nx.is_directed_acyclic_graph(G_med), "DAG B contains a cycle!"

    return G_total, G_med


def render_dags(G_total, G_med, output_path='causal_analysis_output/swe_agent_dags.png'):
    """Renders side-by-side causal diagrams and saves high-DPI PNG."""
    fig, axes = plt.subplots(1, 2, figsize=(20, 9), dpi=300)
    plt.subplots_adjust(wspace=0.15)

    colors = {
        'treatment': '#4E79A7',   # Steel Blue
        'covariate': '#76B7B2',   # Teal
        'mediator1': '#F28E2B',   # Orange
        'mediator2': '#EDC948',   # Gold
        'outcome':   '#59A14F'    # Green
    }

    # --- Plot DAG A ---
    ax = axes[0]
    pos_total = nx.get_node_attributes(G_total, 'pos')
    node_colors_total = [colors[G_total.nodes[n]['role']] for n in G_total.nodes()]

    nx.draw_networkx_nodes(
        G_total, pos_total, ax=ax, node_color=node_colors_total,
        node_size=3600, alpha=0.95, edgecolors='black', linewidths=1.5
    )
    nx.draw_networkx_edges(
        G_total, pos_total, ax=ax, edge_color='#333333',
        arrows=True, arrowsize=20, width=1.8,
        connectionstyle='arc3,rad=0.05', min_source_margin=28, min_target_margin=28
    )
    nx.draw_networkx_labels(
        G_total, pos_total, {n: n.replace('_', '\n') for n in G_total.nodes()},
        ax=ax, font_size=9.5, font_weight='bold'
    )
    ax.set_title("DAG A: Total Effect & Moderation Model\n(Estimating ATE & CATE)", fontsize=14, fontweight='bold', pad=15)
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(0.0, 1.02)
    ax.axis('off')

    # --- Plot DAG B ---
    ax2 = axes[1]
    pos_med = nx.get_node_attributes(G_med, 'pos')
    node_colors_med = [colors[G_med.nodes[n]['role']] for n in G_med.nodes()]

    nx.draw_networkx_nodes(
        G_med, pos_med, ax=ax2, node_color=node_colors_med,
        node_size=2800, alpha=0.95, edgecolors='black', linewidths=1.5
    )
    cov_edges = [e for e in G_med.edges() if e[0] in ['model', 'instance', 'difficulty']]
    core_edges = [e for e in G_med.edges() if e not in cov_edges]

    nx.draw_networkx_edges(
        G_med, pos_med, edgelist=core_edges, ax=ax2, edge_color='#222222',
        arrows=True, arrowsize=16, width=1.5,
        connectionstyle='arc3,rad=0.08', min_source_margin=24, min_target_margin=24
    )
    nx.draw_networkx_edges(
        G_med, pos_med, edgelist=cov_edges, ax=ax2, edge_color='#666666',
        style='dashed', arrows=True, arrowsize=14, width=1.2,
        connectionstyle='arc3,rad=0.10', min_source_margin=24, min_target_margin=24
    )
    nx.draw_networkx_labels(
        G_med, pos_med, {n: n.replace('_', '\n') for n in G_med.nodes()},
        ax=ax2, font_size=8, font_weight='bold'
    )
    ax2.set_title("DAG B: Structural Mechanism & Mediation Model\n(Estimating NDE, NIE & Post-Treatment Pathways)", fontsize=14, fontweight='bold', pad=15)
    ax2.set_xlim(-0.04, 1.04)
    ax2.set_ylim(-0.04, 1.05)
    ax2.axis('off')

    # Shared Legend
    legend_handles = [
        mpatches.Patch(color=colors['treatment'], label='Treatments (Assigned Features)'),
        mpatches.Patch(color=colors['covariate'], label='Pre-Treatment Covariates / Moderators'),
        mpatches.Patch(color=colors['mediator1'], label='Primary Mediators (Evolution Actions)'),
        mpatches.Patch(color=colors['mediator2'], label='Secondary Mediators (Execution & Cost)'),
        mpatches.Patch(color=colors['outcome'], label='Outcome (Task Resolution)')
    ]
    fig.legend(handles=legend_handles, loc='lower center', ncol=3, frameon=True, fontsize=11, bbox_to_anchor=(0.5, 0.01))

    plt.savefig(output_path, bbox_inches='tight', dpi=300)
    print(f"Saved visual DAGs to {output_path}")


def to_dowhy_dot(G):
    """Exports a NetworkX DiGraph into a DOT string compatible with DoWhy's CausalModel."""
    lines = ["digraph {"]
    for u, v in G.edges():
        lines.append(f'    "{u}" -> "{v}";')
    lines.append("}")
    return "\n".join(lines)


if __name__ == "__main__":
    G_total, G_med = build_causal_graphs()
    render_dags(G_total, G_med)

    print("\n--- DoWhy DOT Format (Mediation DAG) ---")
    print(to_dowhy_dot(G_med))