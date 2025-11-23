import json
from pathlib import Path
import click

from mailflow.config import Config
from mailflow.global_index import GlobalIndex
from mailflow.indexer import run_indexer


def register(cli):
    @cli.command()
    @click.option("--base", default="~/Archive", help="Archive base path (entities + indexes)")
    @click.option("--indexes", default=None, help="Indexes path (defaults to <base>/indexes)")
    def index(base, indexes):
        """Build global indexes from the archive filesystem."""
        try:
            count = run_indexer(base, indexes)
            click.echo(f"Indexed {count} document(s)")
        except Exception as e:
            click.echo(f"Indexing failed: {e}", err=True)
            raise SystemExit(1)

    @cli.command()
    @click.argument("query", required=False)
    @click.option("--indexes", default=None, help="Indexes path (defaults to <archive.base_path>/indexes)")
    @click.option("--entity", default=None, help="Filter by entity")
    @click.option("--source", default=None, help="Filter by source")
    @click.option("--workflow", default=None, help="Filter by workflow")
    @click.option("--category", default=None, help="Filter by category")
    @click.option("--limit", default=20, help="Max results")
    def gsearch(query, indexes, entity, source, workflow, category, limit):
        """Search global indexes with optional filters."""
        cfg = Config()
        base = cfg.settings.get("archive", {}).get("base_path", "~/Archive")
        idx_path = indexes or (Path(base).expanduser() / "indexes")
        gi = GlobalIndex(str(idx_path))

        results = list(
            gi.search(
                query or "",
                limit=limit,
                entity=entity,
                source=source,
                workflow=workflow,
                category=category,
            )
        )
        if not results:
            click.echo("No results")
            return

        for r in results:
            click.echo(f"{r['entity']} {r['date']} {r['filename']} [{r.get('workflow') or '-'}]")
            click.echo(f"  {r['rel_path']}")

    @cli.command()
    @click.argument("filepath")
    def data(filepath):
        """Show indexed information for a document (by path or filename)."""
        cfg = Config()
        base = cfg.settings.get("archive", {}).get("base_path", "~/Archive")
        idx_path = Path(base).expanduser() / "indexes"
        gi = GlobalIndex(str(idx_path))

        doc = None
        rel = Path(filepath).as_posix()
        with gi._conn() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE rel_path LIKE ? ORDER BY id DESC LIMIT 1",
                (f"%{rel}",),
            ).fetchone()
            if not row:
                name = Path(filepath).name
                row = conn.execute(
                    "SELECT * FROM documents WHERE filename = ? ORDER BY id DESC LIMIT 1",
                    (name,),
                ).fetchone()
            doc = dict(row) if row else None

        if not doc:
            click.echo(f"No indexed entry found for: {filepath}", err=True)
            raise SystemExit(1)

        click.echo(f"\nDocument: {doc['filename']}  ({doc['entity']})")
        click.echo("=" * 60)
        click.echo(f"Date: {doc['date']}")
        click.echo(f"Type: {doc['type']}")
        click.echo(f"Source: {doc['source']}")
        if doc.get("workflow"):
            click.echo(f"Workflow: {doc['workflow']}")
        if doc.get("category"):
            click.echo(f"Category: {doc['category']}")
        if doc.get("confidence") is not None:
            try:
                click.echo(f"Confidence: {float(doc['confidence']):.2f}")
            except Exception:
                pass
        click.echo(f"Relative path: {doc['rel_path']}")
        click.echo(f"Size: {doc.get('size') or 0} bytes")
        click.echo(f"Hash: {doc.get('hash') or '-'}")
        try:
            origin = json.loads(doc.get("origin_json") or "{}")
        except Exception:
            origin = {}
        if origin:
            click.echo("\nOrigin:")
            for k, v in origin.items():
                if k == "classifier":
                    continue
                click.echo(f"  {k}: {v}")
            if origin.get("classifier"):
                c = origin["classifier"]
                click.echo("\nClassifier:")
                click.echo(
                    f"  suggestion={c.get('workflow_suggestion')} type={c.get('type')} category={c.get('category')} conf={c.get('confidence')}"
                )

