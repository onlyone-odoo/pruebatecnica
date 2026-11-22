===================
Sales Channel Credit
===================

Sales channels, delivery warehouse, invoice journal and credit groups for Odoo 18.

**Table of contents**

.. contents::
   :local:

Configuration
=============

* Sales / Configuration / Sales Channels

  Create a channel with a name. The code (``CH000001``, ``CH000002``, ...) is
  assigned from the ``sale.channel`` sequence and is read-only. Optionally set
  the delivery warehouse and the customer invoice journal. The name is tracked
  on the chatter.

* Sales / Configuration / Credit Groups

  Create a group with a unique code, one sales channel and a global credit in
  the company currency. The code must not contain the text ``026``.

* On the customer, enable *Credit Control* and select at least one credit group.

Usage
=====

The sales channel is required on every sales order.

* The order warehouse becomes the channel warehouse, so the delivery is taken
  from that warehouse.
* The customer invoice created from the order uses the channel journal.
* The channel is copied to the delivery and to the invoice. Sales orders,
  transfers and invoices can be filtered and grouped by channel.

The *Credit* field on the sales order is read-only:

* **No Credit Limit** (grey): the customer has no credit group for this channel.
* **Credit Available** (green): the order total fits in the available credit.
* **Credit Blocked** (red): the order total is greater than the available credit.
  The order cannot be confirmed.

Used credit is the not-yet-invoiced amount of confirmed sales orders plus the
residual of open customer invoices and credit notes, converted to the company
currency. Available credit is the global credit minus the used credit.

Print *Credit Group* from a credit group to list the customers, sales orders
and invoices that feed the used credit.

Credit group API
================

The specification described the JSON body with images that are not part of the
text. This is the contract implemented by the module.

``POST /sale_channel_credit/credit_group/upsert``

* Authentication: an Odoo user with create/write rights on credit groups
  (a sales manager). Send the session cookie obtained from
  ``/web/session/authenticate``.
* Header: ``Content-Type: application/json``.
* The call is all-or-nothing. If one item is invalid, nothing is written.

Request:

.. code-block:: json

    {
      "credit_groups": [
        {
          "code": "GRP-001",
          "name": "North",
          "channel_code": "CH000001",
          "global_credit": 15000.0
        }
      ]
    }

* ``code``: lookup key. Created when missing, otherwise the group is updated.
* ``name``, ``channel_code`` and ``global_credit`` are always required.
* ``channel_code`` must match an existing sales channel of the current company.
* ``global_credit`` is a number in the company currency and cannot be negative.
* ``code`` cannot contain ``026``.

Success (``200``):

.. code-block:: json

    {
      "success": true,
      "credit_groups": [
        {
          "id": 42,
          "code": "GRP-001",
          "name": "North",
          "channel_code": "CH000001",
          "global_credit": 15000.0,
          "currency": "USD",
          "action": "created"
        }
      ]
    }

``action`` is ``created`` or ``updated``.

Error (``400``, or ``403`` when the user has no access):

.. code-block:: json

    {
      "success": false,
      "error": {
        "code": "channel_not_found",
        "message": "No sales channel exists with code \"CH999999\".",
        "channel_code": "CH999999",
        "credit_group_code": "GRP-001"
      }
    }

Error ``code`` values: ``invalid_json``, ``invalid_payload``,
``missing_fields``, ``invalid_credit_group_code``, ``invalid_global_credit``,
``channel_not_found``, ``ambiguous_channel``, ``channel_company_mismatch``,
``credit_group_not_accessible``, ``validation_error``, ``access_error``.

Known limitations
=================

* Documents are counted per channel. A manual invoice without a channel does
  not consume credit.
* A payment in state *In payment* is not treated as open.
* Confirming several orders in a single call checks each one against the
  credit available before any of them is confirmed.
* Down payments are not handled as a special case.

Credits
=======

Authors
~~~~~~~

* Contributors

Maintainers
~~~~~~~~~~~

This module is part of the technical test solution.
