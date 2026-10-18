Feature: Every way to point Examples at a CSV file

  # The plain path is the default form. read('...') is an equivalent spelling.
  # The path is relative to the directory of this .feature file; ".." is allowed,
  # so several features can share one data file.

  Scenario Outline: plain path - <user>
    Given I open the login page
    When I sign in with user "<user>" and password "<password>"
    Then I see the message "<message>"

    Examples:
      | ../data/credentials.csv |

  Scenario Outline: read() with single quotes - <user>
    Given I open the login page
    When I sign in with user "<user>" and password "<password>"
    Then I see the message "<message>"

    Examples:
      | read('../data/credentials.csv') |

  Scenario Outline: read() with double quotes - <user>
    Given I open the login page
    When I sign in with user "<user>" and password "<password>"
    Then I see the message "<message>"

    Examples:
      | read("../data/credentials.csv") |
