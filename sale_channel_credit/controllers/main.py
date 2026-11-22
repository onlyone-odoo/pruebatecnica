# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import json

from odoo import http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request


class CreditGroupApiError(Exception):
    """Business error returned as a JSON body instead of an HTML traceback."""

    def __init__(self, code, message, status=400, **extra):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.extra = extra


class CreditGroupController(http.Controller):
    """Create or update credit groups from an external JSON payload.

    The images that illustrated the JSON contract in the specification are
    not available as text. The request and response shapes are documented
    in the module README.
    """

    @http.route(
        '/sale_channel_credit/credit_group/upsert',
        type='http',
        auth='user',
        methods=['POST'],
        csrf=False,
    )
    def upsert_credit_groups(self):
        """Upsert every credit group of the JSON body in one transaction.

        The lookup key is ``code``. An unknown ``channel_code`` aborts the
        whole request and does not write anything.
        """
        try:
            payload = self._load_payload()
            groups = self._get_group_list(payload)
            prepared = [self._prepare_item(item, index) for index, item in enumerate(groups)]
            with request.env.cr.savepoint():
                results = [self._upsert_item(item) for item in prepared]
        except CreditGroupApiError as error:
            return self._error_response(error)
        except json.JSONDecodeError:
            return self._error_response(CreditGroupApiError(
                'invalid_json',
                'The request body is not valid JSON.',
            ))
        except (ValidationError, UserError) as error:
            return self._error_response(CreditGroupApiError(
                'validation_error',
                str(error),
            ))
        except AccessError:
            return self._error_response(CreditGroupApiError(
                'access_error',
                'You are not allowed to create or update credit groups.',
                status=403,
            ))
        return request.make_json_response({
            'success': True,
            'credit_groups': results,
        })

    def _load_payload(self):
        """Parse the raw HTTP body.

        :return: Decoded JSON value.
        :raise CreditGroupApiError: when the body is empty or not a JSON object.
        """
        raw = request.httprequest.data or b''
        if not raw:
            raise CreditGroupApiError(
                'invalid_payload',
                'The request body is empty.',
            )
        try:
            payload = json.loads(raw.decode('utf-8'))
        except UnicodeDecodeError as error:
            raise CreditGroupApiError(
                'invalid_json',
                'The request body must be UTF-8 JSON.',
            ) from error
        if not isinstance(payload, dict):
            raise CreditGroupApiError(
                'invalid_payload',
                'The JSON root must be an object.',
            )
        return payload

    def _get_group_list(self, payload):
        """Return the list of credit groups sent by the caller."""
        groups = payload.get('credit_groups')
        if not isinstance(groups, list):
            raise CreditGroupApiError(
                'invalid_payload',
                'Field "credit_groups" must be a list.',
            )
        return groups

    def _prepare_item(self, item, index):
        """Validate one list item before any record is written.

        :param item: Raw JSON object.
        :param int index: Position in the list, used in error messages.
        :return: Normalized values.
        :rtype: dict
        """
        if not isinstance(item, dict):
            raise CreditGroupApiError(
                'invalid_payload',
                'Each credit group must be a JSON object.',
                index=index,
            )
        missing = [
            name for name in ('code', 'name', 'channel_code', 'global_credit')
            if item.get(name) in (None, '')
        ]
        if missing:
            raise CreditGroupApiError(
                'missing_fields',
                'Credit group at position %(index)s is missing: %(fields)s.' % {
                    'index': index,
                    'fields': ', '.join(missing),
                },
                index=index,
                credit_group_code=item.get('code') or False,
            )
        code = item['code']
        name = item['name']
        channel_code = item['channel_code']
        if not isinstance(code, str) or not isinstance(name, str) or not isinstance(channel_code, str):
            raise CreditGroupApiError(
                'invalid_payload',
                'Fields "code", "name" and "channel_code" must be strings.',
                index=index,
            )
        if not code.strip() or not name.strip() or not channel_code.strip():
            raise CreditGroupApiError(
                'missing_fields',
                'Credit group at position %(index)s has an empty code, name or channel code.' % {
                    'index': index,
                },
                index=index,
                credit_group_code=code.strip() or False,
            )
        if '026' in code:
            raise CreditGroupApiError(
                'invalid_credit_group_code',
                'The credit group code cannot contain the sequence "026".',
                credit_group_code=code,
            )
        global_credit = self._parse_global_credit(item['global_credit'], code)
        channel = self._get_channel(channel_code, code)
        return {
            'code': code.strip(),
            'name': name.strip(),
            'channel': channel,
            'global_credit': global_credit,
        }

    def _parse_global_credit(self, value, code):
        """Return a non-negative float for the global credit.

        :param value: JSON number or numeric string.
        :param str code: Group code, echoed in the error.
        :rtype: float
        """
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise CreditGroupApiError(
                'invalid_global_credit',
                'Field "global_credit" must be a number.',
                credit_group_code=code,
            )
        try:
            amount = float(value)
        except (TypeError, ValueError) as error:
            raise CreditGroupApiError(
                'invalid_global_credit',
                'Field "global_credit" must be a number.',
                credit_group_code=code,
            ) from error
        if amount < 0:
            raise CreditGroupApiError(
                'invalid_global_credit',
                'Field "global_credit" cannot be negative.',
                credit_group_code=code,
            )
        return amount

    def _get_channel(self, channel_code, credit_group_code):
        """Return the sales channel addressed by its code.

        :raise CreditGroupApiError: when the channel does not exist.
        """
        channels = request.env['sale.channel'].search([
            ('code', '=', channel_code),
        ])
        if not channels:
            raise CreditGroupApiError(
                'channel_not_found',
                'No sales channel exists with code "%s".' % channel_code,
                channel_code=channel_code,
                credit_group_code=credit_group_code,
            )
        if len(channels) > 1:
            raise CreditGroupApiError(
                'ambiguous_channel',
                'Several sales channels exist with code "%s".' % channel_code,
                channel_code=channel_code,
                credit_group_code=credit_group_code,
            )
        channel = channels
        if channel.company_id != request.env.company:
            raise CreditGroupApiError(
                'channel_company_mismatch',
                'Sales channel "%s" belongs to another company.' % channel.display_name,
                channel_code=channel.code,
                credit_group_code=credit_group_code,
            )
        return channel

    def _upsert_item(self, item):
        """Create the credit group or update its name, channel and credit.

        :param dict item: Values returned by :meth:`_prepare_item`.
        :return: JSON object describing the written group.
        :rtype: dict
        """
        group_model = request.env['sale.credit.group']
        group = group_model.search([('code', '=', item['code'])], limit=1)
        if not group:
            # sudo is limited to the existence check. Another company may
            # already own this code, and the record rule would hide it.
            # Creating it again would only raise the unique constraint.
            hidden = group_model.sudo().search([('code', '=', item['code'])], limit=1)
            if hidden:
                raise CreditGroupApiError(
                    'credit_group_not_accessible',
                    'A credit group with code "%s" already exists and cannot be updated with the current company.' % item['code'],
                    credit_group_code=item['code'],
                )
            group = group_model.create({
                'name': item['name'],
                'code': item['code'],
                'channel_id': item['channel'].id,
                'global_credit': item['global_credit'],
                'company_id': request.env.company.id,
            })
            action = 'created'
        else:
            group.write({
                'name': item['name'],
                'channel_id': item['channel'].id,
                'global_credit': item['global_credit'],
            })
            action = 'updated'
        return {
            'id': group.id,
            'code': group.code,
            'name': group.name,
            'channel_code': group.channel_id.code,
            'global_credit': group.global_credit,
            'currency': group.currency_id.name,
            'action': action,
        }

    def _error_response(self, error):
        """Build the JSON error body.

        :param CreditGroupApiError error: Error to serialize.
        :return: HTTP response.
        """
        body = {
            'success': False,
            'error': {
                'code': error.code,
                'message': error.message,
            },
        }
        body['error'].update({
            key: value for key, value in error.extra.items() if value is not None
        })
        return request.make_json_response(body, status=error.status)
