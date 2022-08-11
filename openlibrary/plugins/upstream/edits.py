"""Librarian Edits
"""

import json
import web

from openlibrary import accounts
from openlibrary.core.edits import CommunityEditsQueue, get_status_for_view
from infogami.utils import delegate
from infogami.utils.view import render_template


def response(status='ok', **kwargs):
    return {'status': status, **kwargs}


def process_merge_request(rtype, data):

    user = accounts.get_current_user()
    username = user['key'].split('/')[-1]
    # types can be: create-request, update-request
    if rtype == 'create-request':
        resp = community_edits_queue.create_request(username, **data)
    elif rtype == 'update-request':
        resp = community_edits_queue.update_request(username, **data)
    else:
        resp = response(status='error', error='Unknown request type')
    return resp


class community_edits_queue(delegate.page):
    path = '/merges'

    def GET(self):
        i = web.input(
            page=1, limit=25, mode="open", submitter=None, reviewer=None, order='desc'
        )
        merge_requests = CommunityEditsQueue.get_requests(
            page=int(i.page),
            limit=int(i.limit),
            mode=i.mode,
            submitter=i.submitter,
            reviewer=i.reviewer,
            order=f'created {i.order}',
        ).list()

        total_found = {
            "open": CommunityEditsQueue.get_counts_by_mode(
                mode='open', submitter=i.submitter, reviewer=i.reviewer
            ),
            "closed": CommunityEditsQueue.get_counts_by_mode(
                mode='closed', submitter=i.submitter, reviewer=i.reviewer
            ),
        }
        return render_template(
            'merge_queue/merge_queue',
            total_found,
            merge_requests=merge_requests,
        )

    def POST(self):
        data = json.loads(web.data())
        rtype = data.get('rtype', '')
        if rtype:
            del data['rtype']

        resp = process_merge_request(rtype, data)

        return delegate.RawText(json.dumps(resp), content_type='application/json')

    @staticmethod
    def create_request(username, action='', type=None, olids='', comment: str = None):
        def is_valid_action(action):
            return action in ('create-pending', 'create-merged')

        def needs_unique_url(type):
            return type in (
                CommunityEditsQueue.TYPE['WORK_MERGE'],
                CommunityEditsQueue.TYPE['AUTHOR_MERGE'],
            )

        if is_valid_action(action):
            olid_list = olids.split(',')

            title = community_edits_queue.create_title(type, olid_list)
            url = community_edits_queue.create_url(type, olid_list)

            # Validate URL
            is_valid_url = True
            if needs_unique_url(type) and CommunityEditsQueue.exists(url):
                is_valid_url = False

            if is_valid_url:
                if action == 'create-pending':
                    result = CommunityEditsQueue.submit_request(
                        url, username, title=title, comment=comment, type=type
                    )
                elif action == 'create-merged':
                    result = CommunityEditsQueue.submit_request(
                        url,
                        username,
                        title=title,
                        comment=comment,
                        reviewer=username,
                        status=CommunityEditsQueue.STATUS['MERGED'],
                        type=type,
                    )
                resp = (
                    response(id=result)
                    if result
                    else response(status='error', error='Request creation failed.')
                )
            else:
                resp = response(
                    status='error',
                    error='A merge request for these items already exists.',
                )
        else:
            resp = response(
                status='error',
                error=f'Action "{action}" is invalid for this request type.',
            )

        return resp

    @staticmethod
    def update_request(username, action='', mrid=None, comment=None):
        # Comment on existing request:
        if action == 'comment':
            if comment:
                CommunityEditsQueue.comment_request(mrid, username, comment)
                resp = response()
            else:
                resp = response(status='error', error='No comment sent in request.')
        # Assign to existing request:
        elif action == 'claim':
            result = CommunityEditsQueue.assign_request(mrid, username)
            resp = response(**result)
        # Unassign from existing request:
        elif action == 'unassign':
            CommunityEditsQueue.unassign_request(mrid)
            status = get_status_for_view(CommunityEditsQueue.STATUS['PENDING'])
            resp = response(newStatus=status)
        # Close request by approving:
        elif action == 'approve':
            CommunityEditsQueue.update_request_status(
                mrid, CommunityEditsQueue.STATUS['MERGED'], username, comment=comment
            )
            resp = response()
        # Close request by declining:
        elif action == 'decline':
            CommunityEditsQueue.update_request_status(
                mrid, CommunityEditsQueue.STATUS['DECLINED'], username, comment=comment
            )
            resp = response()
        # Unknown request:
        else:
            resp = response(
                status='error',
                error=f'Action "{action}" is invalid for this request type.',
            )

        return resp

    @staticmethod
    def create_url(type: int, olids: list[str]) -> str:
        if type == CommunityEditsQueue.TYPE['WORK_MERGE']:
            return f'/works/merge?records={",".join(olids)}'
        elif type == CommunityEditsQueue.TYPE['AUTHOR_MERGE']:
            return f'/authors/merge?key={"&key=".join(olids)}'
        return ''

    @staticmethod
    def create_title(type: int, olids: list[str]) -> str:
        if type == CommunityEditsQueue.TYPE['WORK_MERGE']:
            for olid in olids:
                book = web.ctx.site.get(f'/works/{olid}')
                if book and book.title:
                    return book.title
        elif type == CommunityEditsQueue.TYPE['AUTHOR_MERGE']:
            for olid in olids:
                author = web.ctx.site.get(f'/authors/{olid}')
                if author and author.name:
                    return author.name
        return 'Unknown record'


class ui_partials(delegate.page):
    path = '/merges/partials'

    def GET(self):
        i = web.input(type=None, comment='')
        if i.type == 'comment':
            component = render_template('merge_queue/comment', comment_str=i.comment)
            return delegate.RawText(component)


def setup():
    pass
