Feature: Login with data from CSV

  Scenario Outline: Login as <user>/<password>
    Given I open the login page
    When I sign in with user "<user>" and password "<password>"
    Then I see the message "<message>"

    Examples: valid credentials
      | read('data/login.csv') |
