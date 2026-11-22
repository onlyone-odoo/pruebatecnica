# Prueba técnica

Módulo de Odoo 18 (`sale_channel_credit`) para canales de venta y control de crédito por grupo.

La especificación está en [`docs/prueba_tecnica.pdf`](docs/prueba_tecnica.pdf). El detalle funcional y el contrato JSON están en [`sale_channel_credit/README.rst`](sale_channel_credit/README.rst).

## Qué cubre

1. **Canales de venta** en Ventas / Configuración / Sales Channels. Nombre obligatorio, código de solo lectura `CH000001` (secuencia `sale.channel`), depósito y diario de facturas. El cambio de nombre queda en el chatter.
2. **Canal obligatorio en la orden de venta.** El depósito de la orden sale del canal, así que la entrega se prepara desde ese depósito. La factura usa el diario del canal. El canal se copia a la entrega y a la factura, con filtro y agrupar por en órdenes, transferencias y facturas.
3. **Grupos de crédito** en Ventas / Configuración / Credit Groups. Código único que no puede contener `026`, canal obligatorio, crédito global en moneda de la compañía, crédito usado (calculado) y crédito disponible.
4. **Control en el cliente y en la orden.** Si el cliente tiene control de crédito, debe tener al menos un grupo. La orden muestra Crédito en solo lectura: sin límite (gris), disponible (verde) o bloqueado (rojo), en formulario y lista. No se puede confirmar si está bloqueado.
5. **Reporte PDF** del grupo: nombre, código, canal, clientes (nombre, documento, teléfono, correo), órdenes (número, fecha, total) y facturas (número, fecha, importe adeudado).
6. **Endpoint JSON** para crear o actualizar grupos por código.

En la interfaz en inglés los menús se llaman *Sales Channels* y *Credit Groups*, dentro de Sales / Configuration (Ventas / Configuración cuando el idioma es español). Las cadenas están preparadas para traducción.

## Crédito usado

Siempre en moneda de la compañía. Solo entran documentos del canal del grupo y de sus clientes (y contactos):

* órdenes confirmadas, por el importe con impuestos que todavía no está facturado;
* facturas y notas de crédito de cliente publicadas y no pagadas (`not_paid` y `partial`), por el residual en moneda de la compañía.

Así una venta parcial no se cuenta dos veces. Los importes en otra moneda se convierten con la tasa de la fecha del documento. Si el total de la orden es igual al crédito disponible, se puede confirmar: solo se bloquea cuando lo supera.

Si el cliente está en varios grupos del mismo canal, se usa el de menor crédito disponible. Si el contacto no tiene control, se mira la entidad comercial.

## API

`POST /sale_channel_credit/credit_group/upsert`

El PDF mostraba el JSON en imágenes que no quedaron en el texto. Este es el formato.

Hay que estar autenticado (usuario con permiso de crear y editar grupos, por ejemplo un responsable de ventas) y enviar `Content-Type: application/json`. Si un ítem es inválido no se escribe nada.

Pedido:

```json
{
  "credit_groups": [
    {
      "code": "GRP-001",
      "name": "Norte",
      "channel_code": "CH000001",
      "global_credit": 15000.0
    }
  ]
}
```

* `code` busca el grupo. Si no existe, se crea. Si existe, se actualizan nombre, canal y crédito global.
* `channel_code` tiene que ser el código de un canal de la compañía actual.
* `global_credit` es un número en moneda de la compañía y no puede ser negativo.
* `code` no puede contener `026`.

Respuesta correcta (`200`):

```json
{
  "success": true,
  "credit_groups": [
    {
      "id": 42,
      "code": "GRP-001",
      "name": "Norte",
      "channel_code": "CH000001",
      "global_credit": 15000.0,
      "currency": "USD",
      "action": "created"
    }
  ]
}
```

`action` vale `created` o `updated`.

Error (`400`, o `403` si el usuario no tiene permiso):

```json
{
  "success": false,
  "error": {
    "code": "channel_not_found",
    "message": "No sales channel exists with code \"CH999999\".",
    "channel_code": "CH999999",
    "credit_group_code": "GRP-001"
  }
}
```

Otros `error.code`: `invalid_json`, `invalid_payload`, `missing_fields`, `invalid_credit_group_code`, `invalid_global_credit`, `ambiguous_channel`, `channel_company_mismatch`, `credit_group_not_accessible`, `validation_error`, `access_error`.

Ejemplo de sesión y alta:

```bash
curl -c /tmp/odoo.txt -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","params":{"db":"BASE","login":"admin","password":"admin"}}' \
  http://localhost:8069/web/session/authenticate

curl -b /tmp/odoo.txt -H 'Content-Type: application/json' \
  -d '{"credit_groups":[{"code":"GRP-001","name":"Norte","channel_code":"CH000001","global_credit":15000}]}' \
  http://localhost:8069/sale_channel_credit/credit_group/upsert
```

## Instalación

Depende de `sale_management`, `sale_stock`, `account` y `mail`. Versión del módulo: `18.0.1.0.0`.

```bash
odoo-bin -d BASE -i sale_channel_credit --stop-after-init
```

## Decisiones y límites

* La secuencia `CH000001` avanza con cada canal creado. El texto de la especificación dice «cada cliente»; el campo está en el canal.
* El crédito usado se filtra por canal para no descontar la misma venta en todos los grupos del cliente.
* Una factura manual sin canal no entra en el crédito.
* Un pago en estado *in payment* no se considera impago.
* Confirmar varias órdenes a la vez evalúa cada una antes de confirmar ninguna.
* Los anticipos no tienen un tratamiento especial.
* No se generó archivo de traducción: las etiquetas están en inglés y se pueden traducir.

## Tests

`TransactionCase` y `HttpCase`, con la etiqueta `post_install` y sin `at_install`. Cubren la secuencia, la restricción `026` y la unicidad, el crédito en otra moneda, el estado de crédito y el bloqueo de la confirmación, la propagación de depósito y diario, y el endpoint.
