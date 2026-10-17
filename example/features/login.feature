Feature: Login with data from CSV

  Scenario Outline: Login as <user>/<password>
    Given I open the login page
    When I sign in with user "<user>" and password "<password>"
    Then I see the message "<message>"

    Examples: valid credentials
      | read('data/login.csv') |

    Examples: written by hand
      | user  | password | message             |
      | guest | guest    | Invalid credentials |

    @expected_fail
    Examples: fails on purpose
      | read('data/login_fail.csv') |
