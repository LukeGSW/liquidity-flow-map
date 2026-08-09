"""
charts.py — Funzioni grafiche Plotly (tema dark) per la Liquidity Flow Map.

Ogni funzione riceve DataFrame già calcolati e restituisce una go.Figure
pronta per st.plotly_chart(). Nessun fetch, nessun calcolo di pipeline qui.
"""

import pandas as pd
import plotly.graph_objects as go

COLORS = {
    "primary":    "#2196F3",
    "secondary":  "#FF9800",
    "positive":   "#4CAF50",
    "negative":   "#F44336",
    "neutral":    "#9E9E9E",
    "background": "#1E1E2E",
    "surface":    "#2A2A3E",
    "text":       "#E0E0E0",
    "accent":     "#AB47BC",
}


def _base_layout(title: str, x_title: str = "", y_title: str = "") -> dict:
    """Layout Plotly condiviso da tutti i grafici."""
    return dict(
        title=dict(text=title, font=dict(size=16, color=COLORS["text"])),
        paper_bgcolor=COLORS["background"],
        plot_bgcolor=COLORS["surface"],
        font=dict(color=COLORS["text"], family="Inter, Arial, sans-serif"),
        xaxis=dict(title=x_title, showgrid=True, gridcolor="#333355",
                   zeroline=False, color=COLORS["text"]),
        yaxis=dict(title=y_title, showgrid=True, gridcolor="#333355",
                   zeroline=False, color=COLORS["text"]),
        legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor="#444466"),
        hovermode="x unified",
        margin=dict(l=60, r=20, t=60, b=60),
    )


def build_river(shares: pd.DataFrame, colors: dict, title: str) -> go.Figure:
    """
    "Il fiume": area impilata al 100% delle quote di dollar volume.

    Args:
        shares: DataFrame [date x gruppi] con quote in [0, 1]
        colors: dict gruppo -> colore esadecimale
        title:  titolo del grafico
    """
    fig = go.Figure()
    for g in shares.columns:
        fig.add_trace(go.Scatter(
            x=shares.index, y=shares[g] * 100.0,
            name=g, mode="lines",
            line=dict(width=0.5, color=colors.get(g, COLORS["neutral"])),
            stackgroup="one",
            hovertemplate="%{y:.1f}%",
        ))
    layout = _base_layout(title, "", "Quota del dollar volume")
    layout["yaxis"]["range"] = [0, 100]
    layout["yaxis"]["ticksuffix"] = "%"
    layout["legend"] = dict(orientation="h", yanchor="top", y=-0.08,
                            bgcolor="rgba(0,0,0,0)")
    fig.update_layout(**layout)
    return fig


def build_heatmap(panel: pd.DataFrame, title: str, colorbar_title: str,
                  zmin: float, zmax: float, colorscale: str = "RdBu_r") -> go.Figure:
    """
    Heatmap [gruppi x tempo] di una metrica divergente centrata su zero
    (z-score di attenzione oppure pressione firmata).

    Args:
        panel: DataFrame [date x gruppi], già ricampionato (settimanale/mensile)
    """
    fig = go.Figure(go.Heatmap(
        z=panel.T.values,
        x=panel.index,
        y=list(panel.columns),
        colorscale=colorscale, zmid=0.0, zmin=zmin, zmax=zmax,
        hovertemplate="%{y} | %{x|%d/%m/%Y} | %{z:.2f}<extra></extra>",
        colorbar=dict(title=colorbar_title, tickfont=dict(color=COLORS["text"])),
    ))
    layout = _base_layout(title)
    layout["xaxis"]["showgrid"] = False
    layout["yaxis"]["showgrid"] = False
    layout["yaxis"]["autorange"] = "reversed"
    layout["hovermode"] = "closest"
    fig.update_layout(**layout)
    return fig


def build_rotation_bars(delta: pd.Series, title: str) -> go.Figure:
    """
    Barre divergenti della rotazione: Δquota per gruppo su una finestra.

    Deliberatamente NON un Sankey settore->settore: dai dati si conoscono solo
    i saldi netti per gruppo, non gli accoppiamenti "da chi a chi" — un Sankey
    inventerebbe una precisione che non esiste.

    Args:
        delta: Serie gruppo -> Δquota in punti percentuali
    """
    delta = delta.sort_values()
    bar_colors = [COLORS["positive"] if v >= 0 else COLORS["negative"]
                  for v in delta.values]
    fig = go.Figure(go.Bar(
        x=delta.values, y=list(delta.index), orientation="h",
        marker_color=bar_colors,
        text=[f"{v:+.2f} pp" for v in delta.values],
        textposition="outside",
        hovertemplate="%{y}: %{x:+.2f} pp<extra></extra>",
    ))
    layout = _base_layout(title, "Variazione della quota (punti percentuali)", "")
    layout["hovermode"] = "closest"
    fig.update_layout(**layout, showlegend=False)
    fig.add_vline(x=0, line_color=COLORS["neutral"], line_width=1)
    return fig


def build_liquidity_track(z_panel: pd.DataFrame, momentum_window: int,
                          trail: int, colors: dict, title: str) -> go.Figure:
    """
    "Pista della liquidità": scatter livello vs momentum dell'attenzione.

    x = z-score della quota (quanto il gruppo è sopra/sotto la propria norma)
    y = variazione dello z su `momentum_window` periodi (accelerazione)
    Ogni gruppo ha una scia degli ultimi `trail` periodi.

    Quadranti: alto-dx = caldo e in accelerazione; basso-dx = caldo ma in
    raffreddamento; basso-sx = freddo e ignorato; alto-sx = freddo ma in
    riscaldamento (di solito il quadrante più interessante).

    Args:
        z_panel: DataFrame [date x gruppi] di z-score, già ricampionato
    """
    dz = z_panel.diff(momentum_window)
    fig = go.Figure()
    for g in z_panel.columns:
        joint = pd.concat([z_panel[g], dz[g]], axis=1, keys=["z", "dz"]).dropna()
        if joint.empty:
            continue
        tail = joint.iloc[-trail:]
        color = colors.get(g, COLORS["neutral"])
        fig.add_trace(go.Scatter(
            x=tail["z"], y=tail["dz"], mode="lines",
            line=dict(color=color, width=1), opacity=0.35,
            showlegend=False, hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=[tail["z"].iloc[-1]], y=[tail["dz"].iloc[-1]],
            mode="markers+text", name=g,
            marker=dict(size=11, color=color),
            text=[g], textposition="top center",
            textfont=dict(size=11, color=color),
            hovertemplate=g + ": z=%{x:.2f}, Δz=%{y:.2f}<extra></extra>",
        ))
    layout = _base_layout(title, "Attenzione (z-score)", "Momentum dell'attenzione (Δz)")
    layout["hovermode"] = "closest"
    fig.update_layout(**layout, showlegend=False)
    fig.add_hline(y=0, line_color=COLORS["neutral"], line_width=1, opacity=0.5)
    fig.add_vline(x=0, line_color=COLORS["neutral"], line_width=1, opacity=0.5)
    return fig
