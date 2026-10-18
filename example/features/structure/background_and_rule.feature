Feature: Background and Rule with CSV Examples

  Background:
    Given I open the login page

  Rule: Wrong credentials are rejected

    Scenario Outline: Reject <user> with password <password>
      When I sign in with user "<user>" and password "<password>"
      Then I see the message "<message>"

      Examples:
        | data/invalid.csv |
