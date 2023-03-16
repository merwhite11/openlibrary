import re
from typing import Optional

from openlibrary.catalog.marc.get_subjects import subjects_for_work
from openlibrary.catalog.marc.marc_base import BadMARC, NoTitle, MarcException
from openlibrary.catalog.utils import (
    pick_first_date,
    remove_trailing_dot,
    remove_trailing_number_dot,
    tidy_isbn,
)

DNB_AGENCY_CODE = 'DE-101'
max_number_of_pages = 50000  # no monograph should be longer than 50,000 pages
re_bad_char = re.compile('\ufffd')
re_question = re.compile(r'^\?+$')
re_lccn = re.compile(r'([ \dA-Za-z\-]{3}[\d/-]+).*')
re_oclc = re.compile(r'^\(OCoLC\).*?0*(\d+)')
re_ocolc = re.compile('^ocolc *$', re.I)
re_ocn_or_ocm = re.compile(r'^oc[nm]0*(\d+) *$')
re_int = re.compile(r'\d{2,}')
re_number_dot = re.compile(r'\d{3,}\.$')
re_bracket_field = re.compile(r'^\s*(\[.*\])\.?\s*$')


def strip_foc(s):
    foc = '[from old catalog]'
    return s[: -len(foc)].rstrip() if s.endswith(foc) else s


class SeeAlsoAsTitle(MarcException):
    pass


# FIXME: This is SUPER hard to find when needing to add a new field. Why not just decode everything?
FIELDS_WANTED = (
    [
        '001',
        '003',  # for OCLC
        '008',  # publish date, country and language
        '010',  # lccn
        '016',  # National Bibliographic Agency Control Number (for DNB)
        '020',  # isbn
        '022',  # issn
        '035',  # oclc
        '041',  # languages
        '050',  # lc classification
        '082',  # dewey
        '100',
        '110',
        '111',  # authors
        '130',
        '240',  # work title
        '245',  # title
        '250',  # edition
        '260',
        '264',  # publisher
        '300',  # pagination
        '440',
        '490',
        '830',  # series
    ]
    + [str(i) for i in range(500, 588)]
    + [  # notes + toc + description
        # 6XX subjects are extracted separately by get_subjects.subjects_for_work()
        '700',
        '710',
        '711',
        '720',  # contributions
        '246',
        '730',
        '740',  # other titles
        '852',  # location
        '856',  # electronic location / URL
    ]
)


def read_dnb(rec):
    fields = rec.get_fields('016')
    for f in fields:
        (source,) = f.get_subfield_values('2') or [None]
        (control_number,) = f.get_subfield_values('a') or [None]
        if source == DNB_AGENCY_CODE and control_number:
            return {'dnb': [control_number]}


def read_issn(rec):
    fields = rec.get_fields('022')
    if not fields:
        return
    found = []
    for f in fields:
        for k, v in f.get_subfields(['a']):
            issn = v.strip()
            if issn:
                found.append(issn)
    return {'issn': found}


def read_lccn(rec):
    fields = rec.get_fields('010')
    if not fields:
        return
    found = []
    for f in fields:
        for k, v in f.get_subfields(['a']):
            lccn = v.strip()
            if re_question.match(lccn):
                continue
            m = re_lccn.search(lccn)
            if not m:
                continue
            lccn = m.group(1).strip()
            # zero-pad any dashes so the final digit group has size = 6
            lccn = lccn.replace('-', '0' * (7 - (len(lccn) - lccn.find('-'))))
            if lccn:
                found.append(lccn)
    return found


def remove_duplicates(seq):
    u = []
    for x in seq:
        if x not in u:
            u.append(x)
    return u


def read_oclc(rec):
    found = []
    tag_001 = rec.get_fields('001')
    tag_003 = rec.get_fields('003')
    if tag_001 and tag_003 and re_ocolc.match(tag_003[0]):
        oclc = tag_001[0]
        m = re_ocn_or_ocm.match(oclc)
        if m:
            oclc = m.group(1)
        if oclc.isdigit():
            found.append(oclc)

    for f in rec.get_fields('035'):
        for k, v in f.get_subfields(['a']):
            m = re_oclc.match(v)
            if not m:
                m = re_ocn_or_ocm.match(v)
                if m and not m.group(1).isdigit():
                    m = None
            if m:
                oclc = m.group(1)
                if oclc not in found:
                    found.append(oclc)
    return remove_duplicates(found)


def read_lc_classification(rec):
    fields = rec.get_fields('050')
    if not fields:
        return
    found = []
    for f in fields:
        contents = f.get_contents(['a', 'b'])
        if 'b' in contents:
            b = ' '.join(contents['b'])
            if 'a' in contents:
                found += [' '.join([a, b]) for a in contents['a']]
            else:
                found += [b]
        # https://openlibrary.org/show-marc/marc_university_of_toronto/uoft.marc:671135731:596
        elif 'a' in contents:
            found += contents['a']
    return found


def read_isbn(rec):
    fields = rec.get_fields('020')
    if not fields:
        return
    found = []
    for f in fields:
        isbn = rec.read_isbn(f)
        if isbn:
            found += isbn
    ret = {}
    seen = set()
    for i in tidy_isbn(found):
        if i in seen:  # avoid dups
            continue
        seen.add(i)
        if len(i) == 13:
            ret.setdefault('isbn_13', []).append(i)
        elif len(i) <= 16:
            ret.setdefault('isbn_10', []).append(i)
    return ret


def read_dewey(rec):
    fields = rec.get_fields('082')
    if not fields:
        return
    found = []
    for f in fields:
        found += f.get_subfield_values(['a'])
    return found


def read_work_titles(rec):
    found = []
    if tag_240 := rec.get_fields('240'):
        for f in tag_240:
            title = f.get_subfield_values(['a', 'm', 'n', 'p', 'r'])
            found.append(remove_trailing_dot(' '.join(title).strip(',')))
    if tag_130 := rec.get_fields('130'):
        for f in tag_130:
            title = title_from_list(
                [v for k, v in f.get_all_subfields() if k.islower() and k != 'n']
            )
            found.append(title)
    return remove_duplicates(found)


def title_from_list(title_parts, delim=' '):
    # For cataloging punctuation complexities, see https://www.oclc.org/bibformats/en/onlinecataloging.html#punctuation
    STRIP_CHARS = r' /,;:='  # Typical trailing punctuation for 245 subfields in ISBD cataloging standards
    return delim.join(remove_trailing_dot(s.strip(STRIP_CHARS)) for s in title_parts)


def read_title(rec):
    fields = rec.get_fields('245') or rec.get_fields('740')
    if not fields:
        raise NoTitle('No Title found in either 245 or 740 fields.')
    # example MARC record with multiple titles:
    # https://openlibrary.org/show-marc/marc_western_washington_univ/wwu_bibs.mrc_revrev.mrc:299505697:862
    contents = fields[0].get_contents(['a', 'c', 'h'])
    linkages = fields[0].get_contents(['6'])
    bnps = [f for f in fields[0].get_subfield_values(['b', 'n', 'p', 's']) if f]
    ret = {}
    title = alternate = None
    if '6' in linkages:
         alternate = rec.get_linkage('245', linkages['6'][0])
    # MARC record with 245$a missing:
    # https://openlibrary.org/show-marc/marc_western_washington_univ/wwu_bibs.mrc_revrev.mrc:516779055:1304
    if 'a' in contents:
        title = title_from_list(contents['a'])
    elif bnps:
        title = title_from_list([bnps.pop(0)])
    # talis_openlibrary_contribution/talis-openlibrary-contribution.mrc:183427199:255
    if title in ('See', 'See also'):
        raise SeeAlsoAsTitle(f'Title is: {title}')
    # talis_openlibrary_contribution/talis-openlibrary-contribution.mrc:5654086:483
    if title is None:
        subfields = list(fields[0].get_lower_subfield_values())
        title = title_from_list(subfields)
        if not title:  # ia:scrapbooksofmoun03tupp
            raise NoTitle('No title found from joining subfields.')
    if alternate:
        ret['other_titles'] = [title]
        alternate = alternate.get_contents(['a'])
        ret['title'] = title_from_list(alternate['a'])
    else:
        ret['title'] = title

    # Subtitle
    if bnps:
        ret['subtitle'] = title_from_list(bnps, delim=' : ')
    # By statement
    if 'c' in contents:
        ret['by_statement'] = remove_trailing_dot(' '.join(contents['c']))
    # Physical format
    if 'h' in contents:
        h = ' '.join(contents['h']).strip(' ')
        m = re_bracket_field.match(h)
        if m:
            h = m.group(1)
        assert h
        ret['physical_format'] = h
    return ret


def read_edition_name(rec):
    fields = rec.get_fields('250')
    if not fields:
        return
    found = []
    for f in fields:
        found += f.get_lower_subfield_values()
    return ' '.join(found).strip('[]')


lang_map = {
    'ser': 'srp',  # https://www.archive.org/details/zadovoljstvauivo00lubb
    'end': 'eng',
    'enk': 'eng',
    'ent': 'eng',
    'cro': 'chu',
    'jap': 'jpn',
    'fra': 'fre',
    'gwr': 'ger',
    'sze': 'slo',
    'fr ': 'fre',
    'fle': 'dut',  # Flemish -> Dutch
    'it ': 'ita',
}


def read_original_languages(rec):
    if fields := rec.get_fields('041'):
        found = []
        for f in fields:
            is_translation = f.ind1() == '1'
            found += [
                i.lower() for i in f.get_subfield_values('h') if i and len(i) == 3
            ]
        return [lang_map.get(i, i) for i in found if i != 'zxx']


def read_languages(rec, lang_008: Optional[str] = None):
    """Read languages from 041, if present, and combine with language from 008:35-37"""
    found = []
    if lang_008:
        lang_008 = lang_008.lower()
        if lang_008 not in ('   ', '###', '|||', '', '???', 'zxx', 'n/a'):
            found.append(lang_008)

    for f in rec.get_fields('041'):
        if f.ind2() == '7':
            code_source = ' '.join(f.get_subfield_values('2'))
            # TODO: What's the best way to handle these?
            raise MarcException("Non-MARC language code(s), source = ", code_source)
            continue  # Skip anything which is using a non-MARC code source e.g. iso639-1
        for value in f.get_subfield_values('a'):
            if len(value) % 3 == 0:
                # Obsolete cataloging practice was to concatenate all language codes in a single subfield
                for k in range(0, len(value), 3):
                    code = value[k : k + 3].lower()
                    if code != 'zxx' and code not in found:
                        found.append(code)
            else:
                raise MarcException("Got non-multiple of three language code")
    return [lang_map.get(code, code) for code in found]


def read_pub_date(rec):
    fields = rec.get_fields('260')
    if not fields:
        return
    found = []
    for f in fields:
        found += [v for v in f.get_subfield_values('c') if v]
    return remove_trailing_number_dot(found[0].strip('[]')) if found else None


def read_publisher(rec):
    fields = rec.get_fields('260') or rec.get_fields('264')[:1]
    if not fields:
        return
    publisher = []
    publish_places = []
    for f in fields:
        f.remove_brackets()
        contents = f.get_contents(['a', 'b'])
        if 'b' in contents:
            publisher += [x.strip(" /,;:") for x in contents['b']]
        if 'a' in contents:
            publish_places += [x.strip(" /.,;:") for x in contents['a'] if x]
    edition = {}
    if publisher:
        edition["publishers"] = publisher
    if len(publish_places) and publish_places[0]:
        edition["publish_places"] = publish_places
    return edition


def read_author_person(f):
    f.remove_brackets()
    author = {}
    contents = f.get_contents(['a', 'b', 'c', 'd', 'e'])
    if 'a' not in contents and 'c' not in contents:
        return  # should at least be a name or title
    name = [v.strip(' /,;:') for v in f.get_subfield_values(['a', 'b', 'c'])]
    if 'd' in contents:
        author = pick_first_date(strip_foc(d).strip(',') for d in contents['d'])
        if 'death_date' in author and author['death_date']:
            death_date = author['death_date']
            if re_number_dot.search(death_date):
                author['death_date'] = death_date[:-1]
    author['name'] = ' '.join(name)
    author['entity_type'] = 'person'
    subfields = [
        ('a', 'personal_name'),
        ('b', 'numeration'),
        ('c', 'title'),
        ('e', 'role'),
    ]
    for subfield, field_name in subfields:
        if subfield in contents:
            author[field_name] = remove_trailing_dot(
                ' '.join([x.strip(' /,;:') for x in contents[subfield]])
            )
    if 'q' in contents:
        author['fuller_name'] = ' '.join(contents['q'])
    for f in 'name', 'personal_name':
        if f in author:
            author[f] = remove_trailing_dot(strip_foc(author[f]))
    return author


# 1. if authors in 100, 110, 111 use them
# 2. if first contrib is 700, 710, or 711 use it
def person_last_name(f):
    v = list(f.get_subfield_values('a'))[0]
    return v[: v.find(', ')] if ', ' in v else v


def last_name_in_245c(rec, person):
    fields = rec.get_fields('245')
    if not fields:
        return
    last_name = person_last_name(person).lower()
    return any(
        any(last_name in v.lower() for v in f.get_subfield_values(['c']))
        for f in fields
    )


def read_authors(rec):
    count = 0
    fields_100 = rec.get_fields('100')
    fields_110 = rec.get_fields('110')
    fields_111 = rec.get_fields('111')
    count = len(fields_100) + len(fields_110) + len(fields_111)
    if count == 0:
        return
    # talis_openlibrary_contribution/talis-openlibrary-contribution.mrc:11601515:773 has two authors:
    # 100 1  $aDowling, James Walter Frederick.
    # 111 2  $aConference on Civil Engineering Problems Overseas.

    found = [f for f in (read_author_person(f) for f in fields_100) if f]
    for f in fields_110:
        f.remove_brackets()
        name = [v.strip(' /,;:') for v in f.get_subfield_values(['a', 'b'])]
        found.append(
            {'entity_type': 'org', 'name': remove_trailing_dot(' '.join(name))}
        )
    for f in fields_111:
        f.remove_brackets()
        name = [v.strip(' /,;:') for v in f.get_subfield_values(['a', 'c', 'd', 'n'])]
        found.append(
            {'entity_type': 'event', 'name': remove_trailing_dot(' '.join(name))}
        )
    if found:
        return found


def read_pagination(rec):
    fields = rec.get_fields('300')
    if not fields:
        return
    pagination = []
    edition = {}
    for f in fields:
        pagination += f.get_subfield_values(['a'])
    if pagination:
        edition['pagination'] = ' '.join(pagination)
        # strip trailing characters from pagination
        edition['pagination'] = edition['pagination'].strip(' ,:;')
        num = []
        for x in pagination:
            num += [int(i) for i in re_int.findall(x.replace(',', ''))]
            num += [int(i) for i in re_int.findall(x)]
        valid = [i for i in num if i < max_number_of_pages]
        if valid:
            edition['number_of_pages'] = max(valid)
    return edition


def read_series(rec):
    found = []
    for tag in ('440', '490', '830'):
        fields = rec.get_fields(tag)
        if not fields:
            continue
        for f in fields:
            this = []
            for k, v in f.get_subfields(['a', 'v']):
                if k == 'v' and v:
                    this.append(v)
                    continue
                v = v.rstrip('.,; ')
                if v:
                    this.append(v)
            if this:
                found += [' -- '.join(this)]
    return found


def read_notes(rec):
    found = []
    for tag in range(500, 595):
        if tag in (505, 520):
            continue
        fields = rec.get_fields(str(tag))
        if not fields:
            continue
        for f in fields:
            found.append(' '.join(f.get_lower_subfield_values()).strip())
    if found:
        return '\n\n'.join(found)


def read_description(rec):
    fields = rec.get_fields('520')
    if not fields:
        return
    found = []
    for f in fields:
        this = [i for i in f.get_subfield_values(['a']) if i]
        found += this
    if found:
        return "\n\n".join(found).strip(' ')


def read_url(rec):
    found = []
    for f in rec.get_fields('856'):
        contents = f.get_contents(['u', 'y', '3', 'z', 'x'])
        if not contents.get('u'):
            continue
        title = (
            contents.get('y')
            or contents.get('3')
            or contents.get('z')
            or contents.get('x', ['External source'])
        )[0].strip()
        found += [{'url': u.strip(), 'title': title} for u in contents['u']]
    return found


def read_other_titles(rec):
    return (
        [' '.join(f.get_subfield_values(['a'])) for f in rec.get_fields('246')]
        + [' '.join(f.get_lower_subfield_values()) for f in rec.get_fields('730')]
        + [
            ' '.join(f.get_subfield_values(['a', 'p', 'n']))
            for f in rec.get_fields('740')
        ]
    )


def read_location(rec):
    fields = rec.get_fields('852')
    if not fields:
        return
    found = set()
    for f in fields:
        found = found.union({v for v in f.get_subfield_values(['a']) if v})
    return list(found)


def read_contributions(rec):
    """
    Reads contributors from a MARC record
    and use values in 7xx fields to set 'authors'
    if the 1xx fields do not exist. Otherwise set
    additional 'contributions'

    :param (MarcBinary | MarcXml) rec:
    :rtype: dict
    """
    want = dict(
        (
            ('700', 'abcdeq'),
            ('710', 'ab'),
            ('711', 'acdn'),
            ('720', 'a'),
        )
    )
    ret = {}
    skip_authors = set()
    for tag in ('100', '110', '111'):
        fields = rec.get_fields(tag)
        for f in fields:
            skip_authors.add(tuple(f.get_all_subfields()))

    if not skip_authors:
        for tag, f in rec.read_fields(['700', '710', '711', '720']):
            f = rec.decode_field(f)
            if tag in ('700', '720'):
                if 'authors' not in ret or last_name_in_245c(rec, f):
                    ret.setdefault('authors', []).append(read_author_person(f))
                    skip_authors.add(tuple(f.get_subfields(want[tag])))
                continue
            elif 'authors' in ret:
                break
            if tag == '710':
                name = [v.strip(' /,;:') for v in f.get_subfield_values(want[tag])]
                ret['authors'] = [
                    {'entity_type': 'org', 'name': remove_trailing_dot(' '.join(name))}
                ]
                skip_authors.add(tuple(f.get_subfields(want[tag])))
                break
            if tag == '711':
                name = [v.strip(' /,;:') for v in f.get_subfield_values(want[tag])]
                ret['authors'] = [
                    {
                        'entity_type': 'event',
                        'name': remove_trailing_dot(' '.join(name)),
                    }
                ]
                skip_authors.add(tuple(f.get_subfields(want[tag])))
                break

    for tag, f in rec.read_fields(['700', '710', '711', '720']):
        sub = want[tag]
        cur = tuple(rec.decode_field(f).get_subfields(sub))
        if tuple(cur) in skip_authors:
            continue
        name = remove_trailing_dot(' '.join(strip_foc(i[1]) for i in cur).strip(','))
        ret.setdefault('contributions', []).append(name)  # need to add flip_name
    return ret


def read_toc(rec):
    fields = rec.get_fields('505')
    toc = []
    for f in fields:
        toc_line = []
        for k, v in f.get_all_subfields():
            if k == 'a':
                toc_split = [i.strip() for i in v.split('--')]
                if any(len(i) > 2048 for i in toc_split):
                    toc_split = [i.strip() for i in v.split(' - ')]
                # http://openlibrary.org/show-marc/marc_miami_univ_ohio/allbibs0036.out:3918815:7321
                if any(len(i) > 2048 for i in toc_split):
                    toc_split = [i.strip() for i in v.split('; ')]
                # FIXME:
                # http://openlibrary.org/show-marc/marc_western_washington_univ/wwu_bibs.mrc_revrev.mrc:938969487:3862
                if any(len(i) > 2048 for i in toc_split):
                    toc_split = [i.strip() for i in v.split(' / ')]
                assert isinstance(toc_split, list)
                toc.extend(toc_split)
                continue
            if k == 't':
                if toc_line:
                    toc.append(' -- '.join(toc_line))
                if len(v) > 2048:
                    toc_line = [i.strip() for i in v.strip('/').split('--')]
                else:
                    toc_line = [v.strip('/')]
                continue
            if k.islower():  # Exclude numeric, non-display subfields like $6, $7, $8
                toc_line.append(v.strip(' -'))
        if toc_line:
            toc.append('-- '.join(toc_line))
    found = []
    for i in toc:
        if len(i) > 2048:
            i = i.split('  ')
            found.extend(i)
        else:
            found.append(i)
    return [{'title': i, 'type': '/type/toc_item'} for i in found]


def update_edition(rec, edition, func, field):
    if v := func(rec):
        edition[field] = v


def read_edition(rec):
    """
    Converts MARC record object into a dict representation of an edition
    suitable for importing into Open Library.

    :param (MarcBinary | MarcXml) rec:
    :rtype: dict
    :return: Edition representation
    """
    handle_missing_008 = True
    rec.build_fields(FIELDS_WANTED)
    edition = {}
    tag_008 = rec.get_fields('008')
    if len(tag_008) == 0:
        if not handle_missing_008:
            raise BadMARC("single '008' field required")
    if len(tag_008) > 1:
        len_40 = [f for f in tag_008 if len(f) == 40]
        if len_40:
            tag_008 = len_40
        tag_008 = [min(tag_008, key=lambda f: f.count(' '))]
    if len(tag_008) == 1:
        # assert len(tag_008[0]) == 40
        f = re_bad_char.sub(' ', tag_008[0])
        if not f:
            raise BadMARC("'008' field must not be blank")
        publish_date = f[7:11]

        if publish_date.isdigit() and publish_date != '0000':
            edition["publish_date"] = publish_date
        if f[6] == 't':
            edition["copyright_date"] = f[11:15]
        publish_country = f[15:18]
        if publish_country not in ('|||', '   ', '\x01\x01\x01', '???'):
            edition["publish_country"] = publish_country.strip()
        languages = read_languages(rec, lang_008=f[35:38].lower())
        if languages:
            edition['languages'] = languages
    else:
        assert handle_missing_008
        update_edition(rec, edition, read_languages, 'languages')
        update_edition(rec, edition, read_pub_date, 'publish_date')

    update_edition(rec, edition, read_lccn, 'lccn')
    update_edition(rec, edition, read_dnb, 'identifiers')
    update_edition(rec, edition, read_issn, 'identifiers')
    update_edition(rec, edition, read_authors, 'authors')
    update_edition(rec, edition, read_oclc, 'oclc_numbers')
    update_edition(rec, edition, read_lc_classification, 'lc_classifications')
    update_edition(rec, edition, read_dewey, 'dewey_decimal_class')
    update_edition(rec, edition, read_work_titles, 'work_titles')
    update_edition(rec, edition, read_other_titles, 'other_titles')
    update_edition(rec, edition, read_edition_name, 'edition_name')
    update_edition(rec, edition, read_series, 'series')
    update_edition(rec, edition, read_notes, 'notes')
    update_edition(rec, edition, read_description, 'description')
    update_edition(rec, edition, read_location, 'location')
    update_edition(rec, edition, read_toc, 'table_of_contents')
    update_edition(rec, edition, read_url, 'links')
    update_edition(rec, edition, read_original_languages, 'translated_from')

    edition.update(read_contributions(rec))
    edition.update(subjects_for_work(rec))

    try:
        edition.update(read_title(rec))
    except NoTitle:
        if 'work_titles' in edition:
            assert len(edition['work_titles']) == 1
            edition['title'] = edition['work_titles'][0]
            del edition['work_titles']
        else:
            raise

    for func in (read_publisher, read_isbn, read_pagination):
        v = func(rec)
        if v:
            edition.update(v)
    return edition
