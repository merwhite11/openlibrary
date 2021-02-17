# -*- coding: utf-8 -*-
from .. import utils
import web

def test_url_quote():
    assert utils.url_quote('https://foo bar') == 'https%3A%2F%2Ffoo+bar'
    assert utils.url_quote('abc') == 'abc'
    assert utils.url_quote('Kabitā') == 'Kabit%C4%81'
    assert utils.url_quote(u'Kabit\u0101') == 'Kabit%C4%81'


def test_urlencode():
    f = utils.urlencode
    assert f({}) == '', 'empty dict'
    assert f([]) == '', 'empty list'
    assert f({'q': 'hello'}) == 'q=hello', 'basic dict'
    assert f({'q': ''}) == 'q=', 'empty param value'
    assert f({'q': None}) == 'q=None', 'None param value'
    assert f([('q', 'hello')]) == 'q=hello', 'basic list'
    assert f([('x', '3'), ('x', '5')]) == 'x=3&x=5', 'list with multi keys'
    assert f({'q': 'a b c'}) == 'q=a+b+c', 'handles spaces'
    assert f({'q': 'a$$'}) == 'q=a%24%24', 'handles special ascii chars'
    assert f({'q': u'héé'}) == 'q=h%C3%A9%C3%A9'
    assert f({'q': 'héé'}) == 'q=h%C3%A9%C3%A9', 'handles unicode without the u?'
    assert f({'q': 1}) == 'q=1', 'numbers'
    assert f({'q': ['test']}) == 'q=%5B%27test%27%5D', 'list'
    assert f({'q': 'αβγ'}) == 'q=%CE%B1%CE%B2%CE%B3', 'unicode without the u'
    # Can't run this since it's a SyntaxError in python3... But it passes in Python 2
    # assert f({'q': b'αβγ'}) == 'q=%CE%B1%CE%B2%CE%B3', 'byte-string unicode?'
    assert f({'q': u'αβγ'.encode('utf8')}) == 'q=%CE%B1%CE%B2%CE%B3', 'uf8 encoded unicode'
    assert f({'q': u'αβγ'}) == 'q=%CE%B1%CE%B2%CE%B3', 'unicode'


def test_entity_decode():
    assert utils.entity_decode('&gt;foo') == '>foo'
    assert utils.entity_decode('<h1>') == '<h1>'

def test_set_share_links():
    class TestContext(object):
        def __init__(self):
            self.share_links = None
    test_context = TestContext()
    utils.set_share_links(url='https://foo.com', title="bar", view_context=test_context)
    assert test_context.share_links == [
        {'text': 'Facebook', 'url': 'https://www.facebook.com/sharer/sharer.php?u=https%3A%2F%2Ffoo.com'},
        {'text': 'Twitter', 'url': 'https://twitter.com/intent/tweet?url=https%3A%2F%2Ffoo.com&via=openlibrary&text=Check+this+out%3A+bar'},
        {'text': 'Pinterest', 'url': 'https://pinterest.com/pin/create/link/?url=https%3A%2F%2Ffoo.com&description=Check+this+out%3A+bar'}
    ]

def test_set_share_links_unicode():
    # example work that has a unicode title: https://openlibrary.org/works/OL14930766W/Kabit%C4%81
    class TestContext(object):
        def __init__(self):
            self.share_links = None
    test_context = TestContext()
    utils.set_share_links(url=u'https://foo.\xe9', title=u'b\u0101', view_context=test_context)
    assert test_context.share_links == [
        {'text': 'Facebook', 'url': 'https://www.facebook.com/sharer/sharer.php?u=https%3A%2F%2Ffoo.%C3%A9'},
        {'text': 'Twitter', 'url': 'https://twitter.com/intent/tweet?url=https%3A%2F%2Ffoo.%C3%A9&via=openlibrary&text=Check+this+out%3A+b%C4%81'},
        {'text': 'Pinterest', 'url': 'https://pinterest.com/pin/create/link/?url=https%3A%2F%2Ffoo.%C3%A9&description=Check+this+out%3A+b%C4%81'}
    ]

def test_item_image():
    assert utils.item_image('//foo') == 'https://foo'
    assert utils.item_image(None, 'bar') == 'bar'
    assert utils.item_image(None) == None


def test_canonical_url():
    web.ctx.path = '/authors/Ayn_Rand'
    web.ctx.query = ''
    web.ctx.host = 'www.openlibrary.org'
    request = utils.Request()

    url = 'https://www.openlibrary.org/authors/Ayn_Rand'
    assert request.canonical_url == url

    web.ctx.query = '?sort=newest'
    url = 'https://www.openlibrary.org/authors/Ayn_Rand'
    assert request.canonical_url == url

    web.ctx.query = '?page=2'
    url = 'https://www.openlibrary.org/authors/Ayn_Rand?page=2'
    assert request.canonical_url == url

    web.ctx.query = '?page=2&sort=newest'
    url = 'https://www.openlibrary.org/authors/Ayn_Rand?page=2'
    assert request.canonical_url == url

    web.ctx.query = '?sort=newest&page=2'
    url = 'https://www.openlibrary.org/authors/Ayn_Rand?page=2'
    assert request.canonical_url == url

    web.ctx.query = '?sort=newest&page=2&mode=e'
    url = 'https://www.openlibrary.org/authors/Ayn_Rand?page=2'
    assert request.canonical_url == url

    web.ctx.query = '?sort=newest&page=2&mode=e&test=query'
    url = 'https://www.openlibrary.org/authors/Ayn_Rand?page=2&test=query'
    assert request.canonical_url == url

    web.ctx.query = '?sort=new&mode=2'
    url = 'https://www.openlibrary.org/authors/Ayn_Rand'
    assert request.canonical_url == url
