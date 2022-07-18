import logging
import re
from typing import cast, Optional

from openlibrary.solr.solr_types import SolrDocument
from openlibrary.utils import uniq
from openlibrary.utils.isbn import opposite_isbn


logger = logging.getLogger("openlibrary.solr")


re_lang_key = re.compile(r'^/(?:l|languages)/([a-z]{3})$')
re_year = re.compile(r'(\d{4})$')
re_solr_field = re.compile(r'^[-\w]+$', re.U)
re_not_az = re.compile('[^a-zA-Z]')


def is_sine_nomine(pub: str) -> bool:
    """Check if the publisher is 'sn' (excluding non-letter characters)."""
    return re_not_az.sub('', pub).lower() == 'sn'


class EditionSolrBuilder:
    def __init__(self, edition: dict, ia_metadata: dict = None):
        self.edition = edition
        self.ia_metadata = ia_metadata

    def get(self, key: str, default=None):
        return self.edition.get(key, default)

    @property
    def key(self):
        return self.edition['key']

    @property
    def title(self) -> Optional[str]:
        return self.get('title')

    @property
    def subtitle(self) -> Optional[str]:
        return self.get('subtitle')

    @property
    def cover_i(self) -> Optional[int]:
        return next(
            (
                cover_id
                for cover_id in self.get('covers', [])
                if cover_id != -1
            ),
            None
        )

    @property
    def languages(self) -> list[str]:
        """Gets the 3 letter language codes (eg ['ger', 'fre'])"""
        result: list[str] = []
        for lang in self.get('languages', []):
            m = re_lang_key.match(lang['key'] if isinstance(lang, dict) else lang)
            if m:
                result.append(m.group(1))
        return uniq(result)

    @property
    def publisher(self) -> list[str]:
        return uniq(
            publisher if not is_sine_nomine(publisher) else 'Sine nomine'
            for publisher in self.get('publishers', [])
        )

    @property
    def number_of_pages(self) -> Optional[int]:
        if self.get('number_of_pages') and type(self.get('number_of_pages')) == int:
            return cast(int, self.get('number_of_pages'))
        else:
            return None

    @property
    def isbn(self) -> list[str]:
        """
        Get all ISBNs of the given edition. Calculates complementary ISBN13 for each
        ISBN10 and vice-versa. Does not remove '-'s.
        """
        isbns = []

        isbns += [isbn.replace("_", "").strip() for isbn in self.get("isbn_13", [])]
        isbns += [isbn.replace("_", "").strip() for isbn in self.get("isbn_10", [])]

        # Get the isbn13 when isbn10 is present and vice-versa.
        isbns += [opposite_isbn(v) for v in isbns]

        return uniq(isbn for isbn in isbns if isbn)

    @property
    def publish_date(self) -> Optional[str]:
        return self.get('publish_date')

    @property
    def publish_year(self) -> Optional[int]:
        if self.publish_date:
            m = re_year.search(self.publish_date)
            return int(m.group(1)) if m else None
        else:
            return None

    @property
    def ia(self) -> Optional[str]:
        ocaid = self.get('ocaid')
        return ocaid.strip() if ocaid else None

    @property
    def ia_collection(self) -> list[str]:
        if self.ia_metadata:
            return self.ia_metadata.get('collection') or []
        else:
            return []

    @property
    def ia_box_id(self) -> list[str]:
        if self.ia_metadata:
            return self.ia_metadata.get('boxid') or []
        else:
            return []

    @property
    def identifiers(self) -> dict:
        identifiers = {}
        for key, id_list in self.get('identifiers', {}).items():
            solr_key = (
                key.replace('.', '_')
                .replace(',', '_')
                .replace('(', '')
                .replace(')', '')
                .replace(':', '_')
                .replace('/', '')
                .replace('#', '')
                .lower()
            )
            m = re_solr_field.match(solr_key)
            if not m:
                logger.warning(f'Bad identifier on {self.key}: "{key}"')
                continue

            identifiers[f'id_{solr_key}'] = uniq(v.strip() for v in id_list)
        return identifiers


def build_edition_data(edition: dict, ia_metadata: dict) -> SolrDocument:
    """
    Build the solr document for the given edition to store as a nested
    document
    """
    ed = EditionSolrBuilder(edition, ia_metadata)
    solr_doc: SolrDocument = cast(SolrDocument, {
        'key': ed.key,
        'type': 'edition',

        # Display data
        'title': ed.title,
        'subtitle': ed.subtitle,
        'cover_i': ed.cover_i,
        'language': ed.languages,

        # Misc useful data
        'publisher': ed.publisher,
        'publish_date': [ed.publish_date] if ed.publish_date else None,
        'publish_year': [ed.publish_year] if ed.publish_year else None,

        # Identifiers
        'isbn': ed.isbn,
        **ed.identifiers,

        # IA
        'ia': [ed.ia] if ed.ia else None,
        'ia_collection': ed.ia_collection,
        'ia_box_id': ed.ia_box_id,
    })

    return cast(SolrDocument, {
        key: solr_doc[key]  # type: ignore
        for key in solr_doc
        if solr_doc[key] not in (None, [], '')  # type: ignore
    })
