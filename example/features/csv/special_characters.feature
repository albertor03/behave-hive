Feature: Special characters in CSV cells

  # A comma inside quotes, a pipe and a percent sign reach the step unchanged.

  Scenario Outline: The text <text> keeps its length
    Then the text "<text>" has <length> characters

    Examples:
      | data/special.csv |
