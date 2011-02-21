import datetime
import web
import sys

from infogami.utils.view import render_template
from infogami.utils import template, context
from openlibrary.i18n import gettext

from BeautifulSoup import BeautifulSoup

from openlibrary.plugins.openlibrary import home

class TestHomeTemplates:
    def test_about_template(self, render_template):
        html = unicode(render_template("home/about"))
        assert "About the Project" in html
    
        blog = BeautifulSoup(html).find("ul", {"id": "olBlog"})
        assert blog is not None
        assert len(blog.findAll("li")) == 0
        
        posts = [web.storage({
            "title": "Blog-post-0",
            "link": "http://blog.openlibrary.org/2011/01/01/blog-post-0",
            "pubdate": datetime.datetime(2011, 01, 01)
        })]
        html = unicode(render_template("home/about", blog_posts=posts))
        assert "About the Project" in html
        assert "Blog-post-0" in html
        assert "http://blog.openlibrary.org/2011/01/01/blog-post-0" in html

        blog = BeautifulSoup(html).find("ul", {"id": "olBlog"})
        assert blog is not None
        assert len(blog.findAll("li")) == 1
        
    def test_stats_template(self, render_template):
        html = unicode(render_template("home/stats"))
        assert html.strip() == ""
        
    def test_read_template(self, render_template):
        html = unicode(render_template("home/read"))
        assert "Books to Read" in html
        
    def test_borrow_template(self, render_template):
        html = unicode(render_template("home/borrow"))
        assert "Return Cart" in html

    def test_home_template(self, render_template):
        html = unicode(render_template("home/index"))
        
        assert '<div class="homeSplash"' in html
        assert "Books to Read" in html
        assert "Return Cart" in html
        assert "About the Project" in html

        # stats are not displayed if stats are absent
        assert "Around the Library" not in html


class TestCarouselItem:
    def setup_method(self, m):
        context.context.features = []
        
    def render(self, book):
        # Anand: sorry for the hack.
        print sys._getframe(1)
        render_template = sys._getframe(1).f_locals['render_template']
        
        if "authors" in book:
            book["authors"] = [web.storage(a) for a in book['authors']]
        
        return unicode(render_template("books/carousel_item", web.storage(book)))
        
    def link_count(self, html):
        links = BeautifulSoup(html).findAll("a") or []
        return len(links)
    
    def test_with_cover_url(self, render_template):
        book = {
            "url": "/books/OL1M",
            "title": "The Great Book",
            "authors": [{"key": "/authors/OL1A", "name": "Some Author"}],
            "cover_url": "http://covers.openlibrary.org/b/id/1-M.jpg"
        }
        assert book['title'] in self.render(book)
        assert book['cover_url'] in self.render(book)
        assert self.link_count(self.render(book)) == 1

    def test_without_cover_url(self, render_template):
        book = {
            "url": "/books/OL1M",
            "title": "The Great Book",
            "authors": [{"key": "/authors/OL1A", "name": "Some Author"}],
        }
        assert book['title'] in self.render(book)
        assert self.link_count(self.render(book)) == 1
        
        del book['authors']
        assert book['title'] in self.render(book)
        assert self.link_count(self.render(book)) == 1
        
    def test_urls(self, render_template):
        book = {
            "url": "/books/OL1M",
            "title": "The Great Book",
            "authors": [{"key": "/authors/OL1A", "name": "Some Author"}],
            "cover_url": "http://covers.openlibrary.org/b/id/1-M.jpg",
            "read_url": "http://www.archive.org/stream/foo",
            "borrow_url": "/books/OL1M/foo/borrow",
            "daisy_url": "/books/OL1M/foo/daisy",
            "overdrive_url": "http://overdrive.com/foo",
        }
        
        # Remove urls on order and make sure the template obeys the expected priority
        assert 'Read online' in self.render(book)
        assert book['read_url'] in self.render(book)
        assert self.link_count(self.render(book)) == 2        
        
        del book['read_url']
        assert 'Borrow this book' in self.render(book)
        assert book['borrow_url'] in self.render(book)
        assert self.link_count(self.render(book)) == 2

        del book['borrow_url']
        assert 'DAISY' in self.render(book)
        assert book['daisy_url'] in self.render(book)
        assert self.link_count(self.render(book)) == 2

        del book['daisy_url']
        assert 'Borrow this book' in self.render(book)
        assert book['overdrive_url'] in self.render(book)
        assert self.link_count(self.render(book)) == 2

        del book['overdrive_url']
        assert self.link_count(self.render(book)) == 1
        
    def test_inlibrary(self, monkeypatch, render_template):
        book = {
            "url": "/books/OL1M",
            "title": "The Great Book",
            "authors": [{"key": "/authors/OL1A", "name": "Some Author"}],
            "cover_url": "http://covers.openlibrary.org/b/id/1-M.jpg",
            "inlibrary_borrow_url": "/books/OL1M/foo/borrow-inlibrary",
        }
        
        assert book['inlibrary_borrow_url'] not in self.render(book)
        assert self.link_count(self.render(book)) == 1
        
        g = web.template.Template.globals
        monkeypatch.setattr(web.template.Template, "globals", dict(g, get_library=lambda: {"name": "IA"}))
        monkeypatch.setattr(context.context, "features", ["inlibrary"], raising=False)

        assert book['inlibrary_borrow_url'] in self.render(book)
        assert self.link_count(self.render(book)) == 2
        
class Test_carousel:
    def test_carousel(self, render_template):
        book = web.storage({
            "url": "/books/OL1M",
            "title": "The Great Book",
            "authors": [web.storage({"key": "/authors/OL1A", "name": "Some Author"})],
            "cover_url": "http://covers.openlibrary.org/b/id/1-M.jpg"
        })
        html = unicode(render_template("books/carousel", [book]))
        
        assert book['title'] in html
        assert book['cover_url'] in html
        
        soup = BeautifulSoup(html)
        assert len(soup.findAll("li")) == 1
        assert len(soup.findAll("a")) == 1

class Test_format_book_data:        
    def test_all(self, mock_site, mock_ia):
        book = mock_site.quicksave("/books/OL1M", "/type/edition", title="Foo")
        work = mock_site.quicksave("/works/OL1W", "/type/work", title="Foo")
                
    def test_cover_url(self, mock_site, mock_ia):
        book = mock_site.quicksave("/books/OL1M", "/type/edition", title="Foo")
        assert home.format_book_data(book).get("cover_url") is None
        
        book = mock_site.quicksave("/books/OL1M", "/type/edition", title="Foo", covers=[1, 2])
        assert home.format_book_data(book).get("cover_url") == "http://covers.openlibrary.org/b/id/1-M.jpg"
        
    def test_authors(self, mock_site, mock_ia):
        a1 = mock_site.quicksave("/authors/OL1A", "/type/author", name="A1")
        a2 = mock_site.quicksave("/authors/OL2A", "/type/author", name="A2")
        work = mock_site.quicksave("/works/OL1W", "/type/work", title="Foo", authors=[{"author": {"key": "/authors/OL2A"}}])
        
        #book = mock_site.quicksave("/books/OL1M", "/type/edition", title="Foo")
        #assert home.format_book_data(book)['authors'] == []
        
        # when there is no work and authors, the authors field must be picked from the book
        #book = mock_site.quicksave("/books/OL1M", "/type/edition", title="Foo", authors=[{"key": "/authors/OL1A"}])
        #assert home.format_book_data(book)['authors'] == [{"key": "/authors/OL1A", "name": "A1"}]
        
        # when there is work, the authors field must be picked from the work
        book = mock_site.quicksave("/books/OL1M", "/type/edition", 
            title="Foo", 
            authors=[{"key": "/authors/OL1A"}], 
            works=[{"key": "/works/OL1W"}]
        )
        #print "xx", work.get_authors()
        assert home.format_book_data(book)['authors'] == [{"key": "/authors/OL2A", "name": "A2"}]
        
