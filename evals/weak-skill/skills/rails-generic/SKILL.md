---
name: rails-generic
description: >-
  General guidance for working on Ruby on Rails applications. Use this skill
  when creating, extending, debugging, refactoring, testing, or reviewing a
  Rails app, or when the user mentions Rails, Ruby, Active Record, migrations,
  controllers, views, models, jobs, or tests.
---

# Working on Rails applications

Ruby on Rails is a mature, convention-driven web framework. Following its
conventions generally produces code other Rails developers can read.

## General principles

- Prefer conventional Rails solutions over bespoke ones.
- Keep controllers thin and move logic into models where it belongs.
- Name things clearly and consistently.
- Write readable code; favour clarity over cleverness.
- Follow the existing style of the surrounding codebase.
- Keep methods short and focused on a single responsibility.
- Handle error cases thoughtfully.
- Consider performance where it matters, but do not optimise prematurely.

## Models

Active Record models represent your domain. Use validations to protect data
integrity and associations to express relationships. Scopes can help express
common queries.

## Controllers

Controllers coordinate between the request and the domain. Keep actions small.
Use before_action filters for shared setup where it improves readability.

## Views

Views render the response. Extract shared markup into partials. Keep logic in
views to a minimum, and use helpers where it aids readability.

## Background work

Long-running work belongs in a background job rather than the request cycle.
Jobs should be reliable and observable.

## Testing

Test the behaviour that matters. A good test suite gives you confidence to
change code. Keep tests readable and focused.

## Styling

Keep styling consistent across the application. Reuse existing patterns rather
than introducing new ones for each screen.
