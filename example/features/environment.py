from playwright.sync_api import sync_playwright


def before_all(context):
    context.pw = sync_playwright().start()
    context.browser = context.pw.chromium.launch()


def before_scenario(context, scenario):
    context.page = context.browser.new_page()


def after_step(context, step):
    if step.status == "failed":
        context.attach("image/png", context.page.screenshot())


def after_scenario(context, scenario):
    context.page.close()


def after_all(context):
    context.browser.close()
    context.pw.stop()
