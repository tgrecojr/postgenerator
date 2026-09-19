"""Author profile form (replaces editing profile.yaml by hand)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import ValidationError

from postgen.store.profile import Profile, load_profile, save_profile
from postgen.web.routes.common import ctx, page, redirect

router = APIRouter()

PLACEHOLDERS = {
    "headline": "Staff Engineer | Platform Reliability | Developer Experience",
    "about": "Paste your LinkedIn About section verbatim. The topic map is derived from it,"
    " so include the areas you actually want to be known for.",
    "off_limits": "One per line, e.g.\nAnything identifying my employer's internal systems"
    "\nVendor endorsements",
}


def _form_values(profile: Profile | None) -> dict[str, str]:
    if profile is None:
        return dict.fromkeys(("name", "headline", "about", "audience", "goals", "off_limits"), "")
    return {
        "name": profile.name,
        "headline": profile.headline,
        "about": profile.about,
        "audience": profile.audience,
        "goals": profile.goals,
        "off_limits": "\n".join(profile.off_limits),
    }


@router.get("/profile", response_class=HTMLResponse)
def show_profile(request: Request) -> HTMLResponse:
    state = ctx(request)
    try:
        profile: Profile | None = load_profile(state.settings.profile_path)
    except FileNotFoundError, ValidationError:
        profile = None
    return page(
        request,
        "profile.html",
        form=_form_values(profile),
        placeholders=PLACEHOLDERS,
        exists=profile is not None,
        error=None,
    )


@router.post("/profile", response_class=HTMLResponse)
def save_profile_form(
    request: Request,
    headline: Annotated[str, Form()],
    about: Annotated[str, Form()],
    name: Annotated[str, Form()] = "",
    audience: Annotated[str, Form()] = "",
    goals: Annotated[str, Form()] = "",
    off_limits: Annotated[str, Form()] = "",
) -> Response:
    state = ctx(request)
    raw = {
        "name": name.strip(),
        "headline": headline.strip(),
        "about": about.strip(),
        "audience": audience.strip(),
        "goals": goals.strip(),
        "off_limits": [line.strip() for line in off_limits.splitlines() if line.strip()],
    }
    data = {k: v for k, v in raw.items() if v or k in ("headline", "about", "off_limits")}
    try:
        profile = Profile.model_validate(data)
        if not profile.headline or not profile.about:
            raise ValueError("headline and about are required")
    except (ValidationError, ValueError) as exc:
        form = dict(raw, off_limits=off_limits)
        return page(
            request,
            "profile.html",
            400,
            form=form,
            placeholders=PLACEHOLDERS,
            exists=False,
            error=str(exc),
        )
    save_profile(state.settings.profile_path, profile)
    return redirect("/profile")
