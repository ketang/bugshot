from ansi_render import ansi_to_html

ESC = "\x1b"


def test_plain_text():
    assert ansi_to_html("hello world") == "hello world"


def test_empty_string():
    assert ansi_to_html("") == ""


def test_html_entities_escaped():
    assert ansi_to_html("<div>&amp;</div>") == "&lt;div&gt;&amp;amp;&lt;/div&gt;"


def test_bold():
    result = ansi_to_html(f"{ESC}[1mbold{ESC}[0m")
    assert 'font-weight:bold' in result
    assert "bold" in result


def test_dim():
    result = ansi_to_html(f"{ESC}[2mdim{ESC}[0m")
    assert 'opacity:0.5' in result


def test_italic():
    result = ansi_to_html(f"{ESC}[3mitalic{ESC}[0m")
    assert 'font-style:italic' in result


def test_underline():
    result = ansi_to_html(f"{ESC}[4munderline{ESC}[0m")
    assert 'text-decoration:underline' in result


def test_strikethrough():
    result = ansi_to_html(f"{ESC}[9mstrike{ESC}[0m")
    assert 'text-decoration:line-through' in result


def test_inverse():
    result = ansi_to_html(f"{ESC}[31;7minverse{ESC}[0m")
    assert 'background-color:#c91b00' in result


def test_reset_clears_all():
    result = ansi_to_html(f"{ESC}[1mbold{ESC}[0m plain")
    assert "plain" in result
    assert result.endswith(" plain")


def test_newlines_preserved():
    result = ansi_to_html("line1\nline2")
    assert "line1\nline2" in result


def test_non_sgr_sequences_stripped():
    result = ansi_to_html(f"{ESC}[Hhello")
    assert result == "hello"
    result = ansi_to_html(f"{ESC}[5;10Hhello")
    assert result == "hello"


def test_dec_private_mode_stripped():
    """DEC private mode sequences like cursor hide/show should be stripped."""
    result = ansi_to_html(f"{ESC}[?25lhidden cursor{ESC}[?25h")
    assert result == "hidden cursor"
