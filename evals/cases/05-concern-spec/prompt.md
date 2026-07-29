Invoices should support soft deletion: mark a record as deleted instead of
destroying the row, exclude deleted records from normal queries, and allow
restoring one.

Put the behaviour somewhere it can be reused by other models later, and wire it
into `Invoice`.

Write the files.
