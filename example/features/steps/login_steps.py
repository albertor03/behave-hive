from pathlib import Path

from behave import given, then, when

APP = Path(__file__).resolve().parents[2] / "app" / "login.html"


@given("I open the login page")
def step_open(context):
    context.page.goto(APP.as_uri())


@when('I sign in with user "{user}" and password "{password}"')
def step_sign_in(context, user, password):
    context.page.fill("#u", user)
    context.page.fill("#p", password)
    context.page.click("#go")


@then('I see the message "{message}"')
def step_message(context, message):
    assert context.page.inner_text("#msg") == message


@then('the text "{text}" has {length:d} characters')
def step_text_length(context, text, length):
    assert len(text) == length, f"{text!r} has {len(text)} characters, not {length}"


@given("these users exist")
def step_users(context):
    context.users = {row["user"]: row["role"] for row in context.table}


@then('the user "{user}" has the role "{role}"')
def step_user_role(context, user, role):
    assert context.users[user] == role


@given("this note")
def step_note(context):
    context.note = context.text


@then("the note has {count:d} lines")
def step_note_lines(context, count):
    assert len(context.note.splitlines()) == count
