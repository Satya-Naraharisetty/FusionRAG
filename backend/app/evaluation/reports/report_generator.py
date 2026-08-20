import csv
import json
import os
from datetime import UTC, datetime
from typing import Any

from app.evaluation.domain.models import RegressionRun
from app.evaluation.infrastructure.persistence.models import SQLAlchemyEvaluationRun


class ReportGenerator:
    """
    Report Generator writes detailed benchmark performance and regression comparison results
    to Markdown, HTML, JSON, and CSV formats.
    """

    def __init__(self, output_dir: str = "data/evaluation") -> None:
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def generate_all_reports(
        self, run: SQLAlchemyEvaluationRun, regression: RegressionRun | None = None
    ) -> dict[str, str]:
        """
        Generates and saves Markdown, JSON, CSV, and HTML reports for a given evaluation run.
        Returns a dict mapping report type to saved file path.
        """
        run_id_str = str(run.id)
        paths = {
            "markdown": os.path.join(self.output_dir, f"report_{run_id_str}.md"),
            "json": os.path.join(self.output_dir, f"report_{run_id_str}.json"),
            "csv": os.path.join(self.output_dir, f"report_{run_id_str}.csv"),
            "html": os.path.join(self.output_dir, f"report_{run_id_str}.html"),
        }

        # Generate JSON Report
        json_data = self._build_json_report(run, regression)
        with open(paths["json"], "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, default=str)

        # Generate CSV Report
        self._write_csv_report(paths["csv"], run)

        # Generate Markdown Report
        markdown_content = self._build_markdown_report(run, regression, json_data)
        with open(paths["markdown"], "w", encoding="utf-8") as f:
            f.write(markdown_content)

        # Generate HTML Report
        html_content = self._build_html_report(run, regression, json_data)
        with open(paths["html"], "w", encoding="utf-8") as f:
            f.write(html_content)

        return paths

    def _build_json_report(
        self, run: SQLAlchemyEvaluationRun, regression: RegressionRun | None
    ) -> dict[str, Any]:
        """
        Builds the canonical JSON dict representation of the run and results.
        """
        results_list: list[dict[str, Any]] = []
        for result_item in run.results:
            results_list.append(
                {
                    "sample_id": result_item.sample_id,
                    "question": result_item.question,
                    "expected_answer": result_item.expected_answer,
                    "actual_answer": result_item.actual_answer,
                    "latency": result_item.latency,
                    "input_tokens": result_item.input_tokens,
                    "output_tokens": result_item.output_tokens,
                    "cost": result_item.cost,
                    "error_category": result_item.error_category,
                    "metrics": result_item.metrics,
                    "retrieved_contexts": result_item.retrieved_contexts,
                }
            )

        averages = {}
        if results_list:
            sums: dict[str, float] = {}
            counts: dict[str, int] = {}
            for row in results_list:
                for name, data in row["metrics"].items():
                    score = data.get("score")
                    if score is not None:
                        sums[name] = sums.get(name, 0.0) + float(score)
                        counts[name] = counts.get(name, 0) + 1
            for name, total in sums.items():
                averages[name] = round(total / counts[name], 3)

        report = {
            "run_id": str(run.id),
            "name": run.name,
            "profile": run.profile,
            "dataset_id": run.dataset_id,
            "dataset_version": run.dataset_version,
            "provider": run.provider,
            "model": run.model,
            "temperature": run.temperature,
            "embedding_model": run.embedding_model,
            "reranker": run.reranker,
            "retrieval_mode": run.retrieval_mode,
            "system_prompt_version": run.system_prompt_version,
            "git_commit": run.git_commit,
            "git_branch": run.git_branch,
            "status": run.status,
            "total_samples": run.total_samples,
            "completed_samples": run.completed_samples,
            "total_input_tokens": run.total_input_tokens,
            "total_output_tokens": run.total_output_tokens,
            "total_cost": run.total_cost,
            "avg_latency": run.avg_latency,
            "max_latency": run.max_latency,
            "created_at": run.created_at,
            "metric_averages": averages,
            "results": results_list,
        }

        if regression:
            report["regression_comparison"] = {
                "baseline_run_id": str(regression.baseline_run_id),
                "passed": regression.passed,
                "metric_deltas": regression.metric_deltas,
                "details": regression.details,
            }

        return report

    def _write_csv_report(self, path: str, run: SQLAlchemyEvaluationRun) -> None:
        """
        Writes basic tabular metrics details to a CSV file.
        """
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "sample_id",
                    "question",
                    "error_category",
                    "latency",
                    "input_tokens",
                    "output_tokens",
                    "cost",
                    "metrics",
                ]
            )
            for r in run.results:
                metrics_str = "; ".join(
                    f"{k}:{v.get('score')}" for k, v in r.metrics.items()
                )
                writer.writerow(
                    [
                        r.sample_id,
                        r.question,
                        r.error_category,
                        r.latency,
                        r.input_tokens,
                        r.output_tokens,
                        r.cost,
                        metrics_str,
                    ]
                )

    def _build_markdown_report(
        self,
        run: SQLAlchemyEvaluationRun,
        regression: RegressionRun | None,
        data: dict[str, Any],
    ) -> str:
        """
        Constructs a structured Markdown summary report.
        """
        md = []
        md.append(f"# RAG Benchmark Report: {run.name}")
        md.append(f"**Date:** {datetime.now(UTC).isoformat()}  ")
        md.append(f"**Run ID:** `{run.id}`  ")
        md.append(f"**Dataset:** `{run.dataset_id}` (v{run.dataset_version})  ")
        md.append(f"**Profile:** `{run.profile}`  \n")

        md.append("## Execution Metadata")
        md.append(f"- **LLM Provider:** `{run.provider}`")
        md.append(f"- **Chat Model:** `{run.model}` (temp: {run.temperature})")
        md.append(f"- **Embedding Model:** `{run.embedding_model}`")
        md.append(f"- **Search Mode:** `{run.retrieval_mode}`")
        md.append(
            f"- **Git Commit:** `{run.git_commit}` (branch: `{run.git_branch}`)\n"
        )

        md.append("## Cost & Latency Metrics")
        md.append(f"- **Total Samples:** {run.total_samples}")
        md.append(
            f"- **Average Latency:** {run.avg_latency:.2f}s (Max: {run.max_latency:.2f}s)"
        )
        md.append(
            f"- **Tokens Used:** {run.total_input_tokens} Input / {run.total_output_tokens} Output"
        )
        md.append(f"- **Estimated Run Cost:** `${run.total_cost:.5f}`\n")

        md.append("## Average Quality Scores")
        md.append("| Metric | Average Score |")
        md.append("| --- | --- |")
        for metric, avg in data["metric_averages"].items():
            md.append(f"| {metric} | {avg:.3f} |")
        md.append("")

        # Extract reranker tradeoff if present
        sample_meta = run.results[0].metadata_json if run.results else {}
        reranker_tradeoff = sample_meta.get("reranker_tradeoff")
        if reranker_tradeoff:
            md.append("## Cross-Encoder Reranker Impact & Latency Tradeoff")
            md.append("| Metric | Without Reranker | With Reranker | Delta |")
            md.append("| --- | ---:| ---:| ---:|")
            md.append(
                f"| MRR | {reranker_tradeoff.get('without_reranker_mrr', 0.0):.3f} | {reranker_tradeoff.get('with_reranker_mrr', 0.0):.3f} | {reranker_tradeoff.get('mrr_delta', 0.0):+.3f} |"
            )
            md.append(
                f"| nDCG | {reranker_tradeoff.get('without_reranker_ndcg', 0.0):.3f} | {reranker_tradeoff.get('with_reranker_ndcg', 0.0):.3f} | {reranker_tradeoff.get('ndcg_delta', 0.0):+.3f} |"
            )
            md.append(
                f"| Precision@K | {reranker_tradeoff.get('without_reranker_precision', 0.0):.3f} | {reranker_tradeoff.get('with_reranker_precision', 0.0):.3f} | {reranker_tradeoff.get('precision_delta', 0.0):+.3f} |"
            )
            md.append("")
            md.append(
                f"- **Reranker Latency:** Avg {reranker_tradeoff.get('reranker_latency_avg_ms', 0.0)}ms (p50: {reranker_tradeoff.get('reranker_latency_p50_ms', 0.0)}ms, p95: {reranker_tradeoff.get('reranker_latency_p95_ms', 0.0)}ms)"
            )
            md.append(
                f"- **Relative Latency Impact:** +{reranker_tradeoff.get('relative_latency_increase_percent', 0.0)}%\n"
            )

        if regression:
            md.append("## Regression Check Status")
            status_text = (
                "🟢 **PASSED**"
                if regression.passed
                else "🔴 **FAILED (REGRESSION DETECTED)**"
            )
            md.append(
                f"**Comparison Status:** {status_text} (compared to baseline run `{regression.baseline_run_id}`)\n"
            )

            md.append("| Metric | Delta | Status |")
            md.append("| --- | --- | --- |")
            for metric, delta in regression.metric_deltas.items():
                icon = "🔺" if delta > 0.01 else ("🔻" if delta < -0.01 else "➖")
                status = (
                    "Regression"
                    if delta < -0.03
                    else ("Improved" if delta > 0.01 else "Stable")
                )
                md.append(f"| {metric} | {delta:+.3f} {icon} | {status} |")
            md.append("")

            reg_list = regression.details.get("regressions", [])
            if reg_list:
                md.append("### ⚠️ Detected Regressions")
                for r in reg_list:
                    if r.get("metric") == "latency":
                        md.append(
                            f"- **Latency Regression:** Baseline {r.get('baseline')}s -> Current {r.get('candidate')}s (+{r.get('latency_increase_percent')}% vs threshold +{r.get('threshold')}%)"
                        )
                    else:
                        md.append(
                            f"- **{r.get('metric')}:** Baseline {r.get('baseline')} -> Current {r.get('candidate')} (Drop: {r.get('delta')} vs allowed {r.get('threshold')})"
                        )
                md.append("")

        md.append("## Error Category Analysis")
        categories: dict[str, int] = {}
        for r in run.results:
            cat = r.error_category
            categories[cat] = categories.get(cat, 0) + 1

        md.append("| Error Classification | Count |")
        md.append("| --- | --- |")
        for cat, count in categories.items():
            md.append(f"| {cat} | {count} |")
        md.append("")

        return "\n".join(md)

    def _build_html_report(
        self,
        run: SQLAlchemyEvaluationRun,
        regression: RegressionRun | None,
        data: dict[str, Any],
    ) -> str:
        """
        Builds a styled HTML representation of the results.
        """
        metric_rows = "".join(
            f"<tr><td>{m}</td><td>{v:.3f}</td></tr>"
            for m, v in data["metric_averages"].items()
        )

        regression_block = ""
        if regression:
            reg_status = (
                "PASSED" if regression.passed else "FAILED (REGRESSION DETECTED)"
            )
            color = "#10B981" if regression.passed else "#EF4444"
            delta_rows = "".join(
                f"<tr><td>{m}</td><td>{d:+.3f}</td></tr>"
                for m, d in regression.metric_deltas.items()
            )
            regression_block = f"""
            <div class="card">
                <h2>Regression Comparison</h2>
                <div style="font-weight: bold; color: {color}; margin-bottom: 10px;">
                    Comparison Status: {reg_status}
                </div>
                <table>
                    <thead>
                        <tr><th>Metric</th><th>Delta</th></tr>
                    </thead>
                    <tbody>
                        {delta_rows}
                    </tbody>
                </table>
            </div>
            """

        errors: dict[str, int] = {}
        for r in run.results:
            errors[r.error_category] = errors.get(r.error_category, 0) + 1
        error_rows = "".join(
            f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in errors.items()
        )

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>RAG Benchmark Report - {run.name}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: #F3F4F6;
            color: #1F2937;
            padding: 20px;
            margin: 0;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
        }}
        h1 {{
            color: #111827;
            border-bottom: 2px solid #E5E7EB;
            padding-bottom: 10px;
        }}
        .card {{
            background: white;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }}
        th, td {{
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #E5E7EB;
        }}
        th {{
            background-color: #F9FAFB;
            color: #374151;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <h1>RAG Benchmark Report: {run.name}</h1>
            <p><strong>Run ID:</strong> {run.id}</p>
            <p><strong>Dataset ID:</strong> {run.dataset_id} (v{run.dataset_version})</p>
            <p><strong>Execution Date:</strong> {run.created_at}</p>
        </div>

        <div class="card">
            <h2>Average Performance Metrics</h2>
            <table>
                <thead>
                    <tr><th>Metric</th><th>Average Score</th></tr>
                </thead>
                <tbody>
                    {metric_rows}
                </tbody>
            </table>
        </div>

        {regression_block}

        <div class="card">
            <h2>Error Classification</h2>
            <table>
                <thead>
                    <tr><th>Category</th><th>Count</th></tr>
                </thead>
                <tbody>
                    {error_rows}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""
        return html
