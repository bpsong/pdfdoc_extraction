from types import SimpleNamespace

from standard_step.split.llamacloud_split_adapter import LlamaCloudSplitAdapter


def test_llamacloud_split_adapter_uploads_for_split_and_normalizes(monkeypatch, tmp_path):
    pdf_path = tmp_path / "bundle.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    calls = {}

    class FakeFiles:
        def create(self, **kwargs):
            calls["file_create"] = kwargs
            return SimpleNamespace(id="file-1")

    class FakeSplit:
        def create(self, **kwargs):
            calls["split_create"] = kwargs
            return SimpleNamespace(id="spl-1", status="processing")

        def get(self, split_job_id, **kwargs):
            calls["split_get"] = {"split_job_id": split_job_id, **kwargs}
            return SimpleNamespace(
                id="spl-1",
                status="completed",
                result=SimpleNamespace(
                    segments=[
                        SimpleNamespace(category="invoice", confidence_category="high", pages=[1, 2]),
                        SimpleNamespace(category="contract", confidence_category="medium", pages=[3]),
                    ]
                ),
            )

    class FakeClient:
        def __init__(self, api_key):
            calls["api_key"] = api_key
            self.files = FakeFiles()
            self.beta = SimpleNamespace(split=FakeSplit())

    import llama_cloud

    monkeypatch.setattr(llama_cloud, "LlamaCloud", FakeClient)

    adapter = LlamaCloudSplitAdapter(
        api_key="key",
        project_id="project",
        allow_uncategorized="omit",
        polling_interval_seconds=0,
    )
    result = adapter.split_pdf(
        str(pdf_path),
        [{"name": "invoice", "description": "Invoice"}],
    )

    assert calls["api_key"] == "key"
    assert calls["file_create"]["purpose"] == "split"
    assert calls["file_create"]["project_id"] == "project"
    assert calls["split_create"]["document_input"] == {"type": "file_id", "value": "file-1"}
    assert calls["split_create"]["configuration"] == {
        "categories": [{"name": "invoice", "description": "Invoice"}],
        "splitting_strategy": {"allow_uncategorized": "omit"},
    }
    assert calls["split_get"] == {"split_job_id": "spl-1", "project_id": "project"}
    assert result.provider_job_id == "spl-1"
    assert [segment.category for segment in result.segments] == ["invoice", "contract"]
    assert result.segments[0].pages == [1, 2]
    assert result.segments[0].page_start == 1
    assert result.segments[0].page_end == 2
