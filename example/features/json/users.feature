Feature: Examples read from a JSON file

  # A JSON file is an array of objects. The keys of the first object are the
  # <placeholder> names and every object has the same keys. Like CSV, the plain
  # path is the default form and read('...') is an equivalent spelling; the path
  # is relative to the directory of this .feature file.

  Scenario Outline: plain path - <user>
    Given I open the login page
    When I sign in with user "<user>" and password "<password>"
    Then I see the message "<message>"

    Examples:
      | data/users.json |

  Scenario Outline: read() - <user>
    Given I open the login page
    When I sign in with user "<user>" and password "<password>"
    Then I see the message "<message>"

    Examples:
      | read('data/users.json') |

  Scenario Outline: JSON and a hand-written table in one outline - <user>
    Given I open the login page
    When I sign in with user "<user>" and password "<password>"
    Then I see the message "<message>"

    Examples: from a JSON file
      | data/users.json |

    Examples: written by hand
      | user  | password | message             |
      | guest | guest    | Invalid credentials |

  # Numbers reach the step as JSON writes them; true, false and null are
  # written as "true", "false" and an empty cell.
  Scenario Outline: numbers - <text>
    Then the text "<text>" has <length> characters

    Examples:
      | data/lengths.json |
