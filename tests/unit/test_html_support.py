'''The helpers that read pages in tests (tests/support/html.py).'''
from tests.support.html import attribute, element, elements, export_button, links, text

PAGE = '''
<div id="box" class="a b">
  <h2>Errors</h2>
  <ul><li><strong>Formula</strong>, <a href="#page-1">law</a> (F2)
      <a href="/interview/3/" class="go">To interview</a></li></ul>
  <script>var hidden = 1;</script>
</div>
<form class="mardmo-export-form">
  <span title="why"><input type="submit" value="Export" class="btn" disabled aria-describedby="x"></span>
  <input type="submit" name="cancel" value="Cancel">
</form>
'''


def test_text_is_what_the_user_reads():
    assert text(element(PAGE, id='box')) == 'Errors Formula, law (F2) To interview'
    assert text('&lt;b&gt; and <b>bold</b>') == '<b> and bold'


def test_elements_by_id_class_tag_and_attribute():
    assert element(PAGE, cls='b').name == 'div'
    assert [attribute(node, 'href') for node in elements(PAGE, tag='a', cls='go')] == ['/interview/3/']
    assert attribute(element(PAGE, tag='input', aria_describedby='x'), 'disabled') == ''
    assert links(element(PAGE, id='box')) == [('law', '#page-1'), ('To interview', '/interview/3/')]


def test_the_export_button():
    assert export_button(PAGE) == 'disabled'
    assert export_button(PAGE.replace(' disabled', '')) == 'enabled'
    assert export_button('<p>no form</p>') is None


def test_a_piece_of_a_page_is_read_as_far_as_it_goes():
    assert text('ure">Relations</h3> - <strong>Missing</strong>') == 'ure">Relations - Missing'
