Feature: Step tables and docstrings

  # Steps keep their own data tables and docstrings. Text inside a docstring is never
  # read as Examples, even when it looks like a CSV reference.

  Scenario: A data table in a step
    Given these users exist
      | user  | role  |
      | admin | owner |
      | guest | read  |
    Then the user "admin" has the role "owner"

  Scenario: A docstring that looks like an Examples table
    Given this note
      """
      Examples:
        | read('data/does_not_exist.csv') |
      """
    Then the note has 2 lines
