from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.directives import DirectiveValidationError, compile_constraints, validate_interpretations
from app.interpreter import InterpretationProvider, InterpretationProviderError, OpenAIInterpreter
from app.models import ErrorResponse, OptimizationRequest, OptimizationResponse
from app.optimizer import OptimizationError, optimize_schedule
from app.replay import ReplayValidationError, replay_plan


def _summary(interpreted_count: int, response: OptimizationResponse) -> str:
    if interpreted_count:
        directive_text = (
            f"Applied {interpreted_count} operator directive(s) after deterministic validation"
        )
    else:
        directive_text = "No operator-note constraints applied after deterministic validation"
    return (
        f"{directive_text}; optimized grid cost is {response.total_cost_bdt:.2f} BDT "
        f"with peak grid use {response.peak_grid_kwh:.2f} kWh."
    )


def create_app(
    settings: Settings | None = None,
    interpreter: InterpretationProvider | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level.upper())

    app = FastAPI(
        title="GridWise LLM Energy Optimizer",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.interpreter = interpreter

    @app.exception_handler(RequestValidationError)
    async def invalid_request_handler(_: Request, __: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": "malformed or structurally invalid request"},
        )

    @app.get("/health", response_model=dict[str, str], responses={500: {"model": ErrorResponse}})
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/optimize-energy",
        response_model=OptimizationResponse,
        responses={
            400: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
        },
    )
    def optimize_energy(payload: OptimizationRequest) -> OptimizationResponse:
        provider = app.state.interpreter
        if provider is None:
            try:
                provider = OpenAIInterpreter(app.state.settings)
                app.state.interpreter = provider
            except InterpretationProviderError as error:
                raise HTTPException(
                    status_code=500, detail="language-model configuration is unavailable"
                ) from error

        try:
            candidates = provider.interpret(payload)
            directives = validate_interpretations(candidates, payload)
        except InterpretationProviderError as error:
            raise HTTPException(
                status_code=500, detail="language-model interpretation failed safely"
            ) from error
        except DirectiveValidationError as error:
            raise HTTPException(
                status_code=500, detail="language-model output failed deterministic validation"
            ) from error

        constraints = compile_constraints(payload, directives)
        try:
            result = optimize_schedule(payload, constraints)
        except OptimizationError as error:
            raise HTTPException(
                status_code=422, detail="scenario is infeasible under the declared constraints"
            ) from error

        try:
            total_grid, total_cost, peak_grid = replay_plan(
                payload, constraints, result.hourly_plan
            )
        except (
            ReplayValidationError
        ) as error:  # A code defect or numerical regression; never return unsafe output.
            raise HTTPException(
                status_code=500, detail="internal schedule validation failed"
            ) from error

        response = OptimizationResponse(
            scenario_id=payload.scenario_id,
            directive_interpretation=directives,
            hourly_plan=result.hourly_plan,
            total_grid_kwh=total_grid,
            total_cost_bdt=total_cost,
            peak_grid_kwh=peak_grid,
            plan_summary="",
        )
        response.plan_summary = _summary(sum(item.applies for item in directives), response)
        return response

    return app


app = create_app()
