from django import template

register = template.Library()


@register.filter
def market_source_label(value):
    """Keep source identity in records while using neutral labels in the interface."""
    if str(value).casefold() == "investorgain":
        return "Market feed"
    return value
