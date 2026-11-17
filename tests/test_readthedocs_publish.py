import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("rtd_publish", ROOT / "scripts/publish_readthedocs.py")
publish = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publish)


class ReadTheDocsPublicationTests(unittest.TestCase):
    def test_credentials_never_sent_to_other_origins_or_redirects(self):
        client = publish.Client("test-credential")
        client.opener = Mock()
        for url in ("https://example.org/api/v3/projects/", "http://app.readthedocs.org/api/v3/",
                    "https://app.readthedocs.org@evil.example/api/v3/", "/accounts/login/"):
            with self.assertRaises(publish.PublicationError):
                client.request("GET", url)
        client.opener.open.assert_not_called()
        with self.assertRaises(publish.PublicationError):
            publish.NoRedirects().redirect_request(None, None, 302, "", {}, "https://example.org/")

    def test_project_name_collision_does_not_modify_another_repository(self):
        client = Mock()
        client.projects.return_value = [{"name": "OpenMolSpec", "slug": "openmolspec",
                                         "repository": {"url": "https://github.com/example/other"}}]
        with self.assertRaisesRegex(publish.PublicationError, "another repository"):
            publish.configure(client, "OpenMolSpec")
        client.request.assert_not_called()

    def test_existing_project_is_reused_and_configured(self):
        client = Mock()
        project = {"name": "OpenMolSpec", "slug": "openmolspec",
                   "repository": {"url": publish.REPOSITORY}, "default_branch": "main"}
        client.projects.return_value = [project]
        client.request.side_effect = [None, dict(project, default_branch=publish.BRANCH,
                                                default_version="latest",
                                                readthedocs_yaml_path=".readthedocs.yaml")]
        with contextlib.redirect_stdout(io.StringIO()):
            endpoint, _ = publish.configure(client, "OpenMolSpec")
        self.assertEqual(endpoint, "/api/v3/projects/openmolspec/")
        self.assertEqual([c.args[0] for c in client.request.call_args_list], ["PATCH", "GET"])

    def test_canonical_name_is_selected_over_legacy_project_for_same_repository(self):
        client = Mock()
        project = {"name": "OpenMolSpec", "slug": "openmolspec",
                   "repository": {"url": publish.REPOSITORY},
                   "default_branch": publish.BRANCH, "default_version": "latest",
                   "readthedocs_yaml_path": ".readthedocs.yaml"}
        client.projects.return_value = [dict(project, name="OpenMolSpec 1.0", slug="openmolspec-10"), project]
        client.request.return_value = project
        with contextlib.redirect_stdout(io.StringIO()):
            endpoint, _ = publish.configure(client, "OpenMolSpec")
        self.assertEqual(endpoint, "/api/v3/projects/openmolspec/")
        client.request.assert_called_once_with("GET", endpoint)

    def test_new_project_uses_returned_slug_and_release_configuration(self):
        client = Mock()
        client.projects.return_value = []
        project = {"name": "OpenMolSpec", "slug": "openmolspec-2",
                   "repository": {"url": publish.REPOSITORY}}
        client.request.side_effect = [project, None, dict(project,
            default_branch=publish.BRANCH, default_version="latest",
            readthedocs_yaml_path=".readthedocs.yaml")]
        with contextlib.redirect_stdout(io.StringIO()):
            endpoint, _ = publish.configure(client, "OpenMolSpec")
        self.assertEqual(endpoint, "/api/v3/projects/openmolspec-2/")
        calls = client.request.call_args_list
        self.assertEqual(calls[0].args[:2], ("POST", "/api/v3/projects/"))
        self.assertEqual(calls[0].args[2]["repository"]["url"], publish.REPOSITORY)
        self.assertEqual(calls[1].args[1], endpoint)

    def test_unpushed_commit_blocks_publication(self):
        remote = subprocess.CompletedProcess([], 0, "b" * 40 + "\trefs/heads/" + publish.BRANCH, "")
        with patch.object(publish, "check_network"), patch.object(publish.subprocess, "run", return_value=remote), \
                patch.object(publish, "Client") as client:
            with self.assertRaisesRegex(publish.PublicationError, "Push the release branch first"):
                publish.main(["--apply", "--expected-commit", "a" * 40])
            client.assert_not_called()

    def test_build_must_finish_successfully_at_expected_commit(self):
        build = {"id": 7, "state": {"code": "building"}, "success": None, "commit": "a" * 40}
        self.assertFalse(publish.build_result(build, "a" * 40)["hosted_build_verified"])
        build.update(state={"code": "finished"}, success=True)
        self.assertFalse(publish.build_result(build, "b" * 40)["hosted_build_verified"])
        self.assertTrue(publish.build_result(build, "a" * 40)["hosted_build_verified"])

    def test_default_plan_does_not_access_network_or_credentials(self):
        with patch.object(publish, "check_network") as network, \
                patch.object(publish.getpass, "getpass") as token, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(publish.main([]), 0)
            network.assert_not_called()
            token.assert_not_called()


if __name__ == "__main__":
    unittest.main()
