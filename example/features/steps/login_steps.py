from pathlib import Path

from behave import given, then, when

# resolve(): behave-hive runs the steps through a symlink from the expanded tree
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
