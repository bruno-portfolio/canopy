from __future__ import annotations

from canopy.render.html import render_html
from canopy.render.svg import render_svg

from .conftest import make_layout, make_mod, make_node, make_pd, make_theme


def _render(**kw) -> str:
    pd = kw.get("pd", make_pd())
    ly = kw.get("ly", make_layout())
    t = kw.get("t", make_theme())
    svg = render_svg(pd, ly, t)
    return render_html(pd, t, svg)


# ── Basic ─────────────────────────────────────────────────────────────────


class TestRenderHtmlBasic:
    def test_render_html_returns_string(self):
        html = _render()
        assert isinstance(html, str)
        assert len(html) > 0

    def test_render_html_valid_structure(self):
        html = _render()
        assert "<!DOCTYPE html>" in html
        assert "<svg" in html
        assert "</html>" in html

    def test_render_html_contains_module_data(self):
        pd = make_pd(modules=[make_mod(name="pkg.alpha"), make_mod(name="pkg.beta")])
        ly = make_layout(nodes=[make_node(name="pkg.alpha"), make_node(name="pkg.beta", x=-100)])
        html = _render(pd=pd, ly=ly)
        assert '"pkg.alpha"' in html
        assert '"pkg.beta"' in html

    def test_render_html_contains_tooltip(self):
        html = _render()
        assert 'class="tooltip"' in html

    def test_render_html_self_contained(self):
        html = _render()
        assert "<link" not in html
        assert 'src="http' not in html

    def test_render_html_contains_theme_colors(self):
        t = make_theme()
        html = _render(t=t)
        assert t.healthy.base in html
        assert t.moderate.base in html
        assert t.complex.base in html

    def test_render_html_svg_responsive(self):
        t = make_theme()
        html = _render(t=t)
        assert 'width="100%"' in html
        import re

        svg_tag = re.search(r"<svg\b[^>]*>", html).group(0)
        assert f'width="{t.width}"' not in svg_tag


# ── Fit to screen ────────────────────────────────────────────────────────


class TestFitToScreen:
    def test_body_no_scroll(self):
        html = _render()
        assert "overflow: hidden" in html

    def test_container_flex_column(self):
        html = _render()
        assert "flex-direction: column" in html

    def test_dvh_support(self):
        html = _render()
        assert "100dvh" in html

    def test_orbital_flex_grow(self):
        html = _render()
        assert "flex: 1" in html
        assert "min-height: 0" in html

    def test_stats_bar_no_shrink(self):
        html = _render()
        assert "flex-shrink: 0" in html


# ── Search / Filter ──────────────────────────────────────────────────────


class TestSearch:
    def test_search_input_exists(self):
        html = _render()
        assert 'id="search-input"' in html
        assert 'placeholder="Search modules..."' in html

    def test_search_clear_button(self):
        html = _render()
        assert 'id="search-clear"' in html

    def test_search_count_span(self):
        html = _render()
        assert 'id="search-count"' in html

    def test_search_dim_css(self):
        html = _render()
        assert ".search-dim" in html
        assert "pointer-events: none" in html

    def test_search_highlight_css(self):
        html = _render()
        assert ".search-highlight" in html

    def test_filter_modules_function(self):
        html = _render()
        assert "function filterModules(query)" in html


# ── Double-click reset ───────────────────────────────────────────────────


class TestDblclickReset:
    def test_dblclick_listener(self):
        html = _render()
        assert "dblclick" in html

    def test_reset_zoom_function(self):
        html = _render()
        assert "function resetZoom()" in html

    def test_transition_cleanup(self):
        """Transition must be cleared after animation to avoid 'soap' effect."""
        html = _render()
        assert "svgEl.style.transition = ''" in html


# ── Tooltip MI color ─────────────────────────────────────────────────────


class TestTooltipMiColor:
    def test_mi_color_function(self):
        html = _render()
        assert "function miColor(mi)" in html

    def test_mi_constants(self):
        t = make_theme()
        html = _render(t=t)
        assert f"MI_HEALTHY = {t.mi_healthy}" in html
        assert f"MI_MODERATE = {t.mi_moderate}" in html

    def test_tooltip_uses_mi_color(self):
        html = _render()
        assert "miEl.style.color = miColor(m.mi)" in html


# ── Sidebar ──────────────────────────────────────────────────────────────


class TestSidebar:
    def test_sidebar_toggle_button(self):
        html = _render()
        assert 'id="sidebar-toggle"' in html

    def test_sidebar_container(self):
        html = _render()
        assert 'id="sidebar"' in html
        assert 'id="sidebar-list"' in html

    def test_sidebar_header(self):
        html = _render()
        assert "sidebar-header" in html

    def test_sidebar_open_class(self):
        html = _render()
        assert "#sidebar.open" in html

    def test_build_sidebar_list_function(self):
        html = _render()
        assert "function buildSidebarList()" in html

    def test_zoom_to_module_function(self):
        html = _render()
        assert "function zoomToModule(name)" in html

    def test_zoom_uses_getBBox(self):
        """Must use DOM getBBox, not JSON coords."""
        html = _render()
        assert "g.getBBox()" in html


# ── Keyboard shortcuts ───────────────────────────────────────────────────


class TestKeyboardShortcuts:
    def test_shortcuts_overlay_exists(self):
        html = _render()
        assert 'id="shortcuts-overlay"' in html

    def test_shortcuts_modal(self):
        html = _render()
        assert "Keyboard Shortcuts" in html
        assert "<kbd>" in html

    def test_keydown_listener(self):
        html = _render()
        assert "document.addEventListener('keydown'" in html

    def test_shortcut_keys(self):
        html = _render()
        assert "e.key === '/'" in html
        assert "e.key === 'Escape'" in html
        assert "e.key === 'r'" in html
        assert "e.key === 'm'" in html
        assert "e.key === '?'" in html

    def test_ignores_input_fields(self):
        html = _render()
        assert "tag === 'INPUT'" in html
