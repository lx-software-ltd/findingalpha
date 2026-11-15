"""Admin group claim shapes."""

from __future__ import annotations

import unittest

from http_common import _groups_include_admin, _require_admin


class GroupsTest(unittest.TestCase):
    def test_list_form(self) -> None:
        self.assertTrue(_groups_include_admin({"cognito:groups": ["admin"]}))
        self.assertFalse(_groups_include_admin({"cognito:groups": ["viewer"]}))

    def test_bracketed_form(self) -> None:
        self.assertTrue(_groups_include_admin({"cognito:groups": "[admin]"}))
        self.assertTrue(_groups_include_admin({"cognito:groups": "[viewer, admin]"}))
        self.assertFalse(_groups_include_admin({"cognito:groups": "[viewer]"}))

    def test_missing_groups_are_not_admin(self) -> None:
        self.assertFalse(_groups_include_admin({}))
        self.assertIsNone(_require_admin({"requestContext": {"authorizer": {"jwt": {"claims": {}}}}}))


if __name__ == "__main__":
    unittest.main()
