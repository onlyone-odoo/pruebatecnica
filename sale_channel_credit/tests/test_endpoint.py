# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import json

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestCreditGroupEndpoint(HttpCase):
    """JSON upsert of credit groups."""

    def _post(self, payload):
        """POST the payload to the upsert endpoint.

        :param dict payload: JSON body.
        :return: HTTP response.
        """
        return self.url_open(
            '/sale_channel_credit/credit_group/upsert',
            data=json.dumps(payload).encode(),
            headers={'Content-Type': 'application/json'},
        )

    def test_upsert_creates_and_updates(self):
        """An unknown code is created and the same code is updated afterwards."""
        self.authenticate('admin', 'admin')
        channel = self.env['sale.channel'].create({'name': 'API Channel'})
        other = self.env['sale.channel'].create({'name': 'Other API Channel'})

        created = self._post({
            'credit_groups': [{
                'code': 'API-1',
                'name': 'Created from API',
                'channel_code': channel.code,
                'global_credit': 1500,
            }],
        })
        self.assertEqual(created.status_code, 200, created.text)
        body = created.json()
        self.assertTrue(body['success'])
        self.assertEqual(body['credit_groups'][0]['action'], 'created')
        self.assertEqual(body['credit_groups'][0]['channel_code'], channel.code)

        self.env.invalidate_all()
        group = self.env['sale.credit.group'].search([('code', '=', 'API-1')])
        self.assertEqual(group.name, 'Created from API')
        self.assertEqual(group.global_credit, 1500.0)
        self.assertEqual(group.channel_id, channel)

        updated = self._post({
            'credit_groups': [{
                'code': 'API-1',
                'name': 'Updated from API',
                'channel_code': other.code,
                'global_credit': 2500.5,
            }],
        })
        self.assertEqual(updated.status_code, 200, updated.text)
        updated_body = updated.json()
        self.assertEqual(updated_body['credit_groups'][0]['action'], 'updated')
        self.assertEqual(updated_body['credit_groups'][0]['id'], group.id)

        self.env.invalidate_all()
        group = self.env['sale.credit.group'].browse(group.id)
        self.assertEqual(group.name, 'Updated from API')
        self.assertEqual(group.channel_id, other)
        self.assertEqual(group.global_credit, 2500.5)

    def test_unknown_channel_returns_json_error_and_writes_nothing(self):
        """A missing channel aborts the whole payload."""
        self.authenticate('admin', 'admin')
        channel = self.env['sale.channel'].create({'name': 'Valid Channel'})
        response = self._post({
            'credit_groups': [
                {
                    'code': 'API-OK',
                    'name': 'Should Not Be Created',
                    'channel_code': channel.code,
                    'global_credit': 10,
                },
                {
                    'code': 'API-BAD',
                    'name': 'Missing Channel',
                    'channel_code': 'CH-DOES-NOT-EXIST',
                    'global_credit': 10,
                },
            ],
        })
        self.assertEqual(response.status_code, 400, response.text)
        body = response.json()
        self.assertFalse(body['success'])
        self.assertEqual(body['error']['code'], 'channel_not_found')
        self.assertEqual(body['error']['channel_code'], 'CH-DOES-NOT-EXIST')
        self.assertFalse(self.env['sale.credit.group'].search([
            ('code', 'in', ['API-OK', 'API-BAD']),
        ]))

    def test_code_containing_026_returns_json_error(self):
        """The 026 restriction is returned as JSON instead of a traceback."""
        self.authenticate('admin', 'admin')
        channel = self.env['sale.channel'].create({'name': 'Constraint Channel'})
        response = self._post({
            'credit_groups': [{
                'code': 'BAD026',
                'name': 'Invalid',
                'channel_code': channel.code,
                'global_credit': 10,
            }],
        })
        self.assertEqual(response.status_code, 400, response.text)
        body = response.json()
        self.assertEqual(body['error']['code'], 'invalid_credit_group_code')
        self.assertFalse(self.env['sale.credit.group'].search([('code', '=', 'BAD026')]))
