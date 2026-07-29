Add a background job that charges an invoice and records a `Payment` row for it.

A nightly sweep enqueues this job, and the queue retries failed jobs.

Write the files.
