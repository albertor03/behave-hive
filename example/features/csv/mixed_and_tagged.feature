Feature: CSV tables and hand-written tables in one outline

  # Each Examples keeps its own name and tags, so a run can pick one of them:
  #   behave-hive run -- --tags=@smoke
  #   behave-hive run -- --tags=@regression

  Scenario Outline: Sign in as <user>
    Given I open the login page
    When I sign in with user "<user>" and password "<password>"
    Then I see the message "<message>"

    @smoke
    Examples: from a CSV file
      | data/smoke.csv |

    @regression
    Examples: written by hand
      | user  | password | message             |
      | guest | guest    | Invalid credentials |

    @regression
    Examples: from another CSV file, with read()
      | read('data/regression.csv') |
