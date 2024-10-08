from __future__ import annotations

from typing import List

from patchwork.common.client.scm import GithubClient, GitlabClient, PullRequestState
from patchwork.logger import logger
from patchwork.step import DataPoint, Step
from patchwork.steps.ReadPRs.typed import ReadPRsInputs

_IGNORED_EXTENSIONS = [
    ".jpeg",
    ".gif",
    ".svg",
    ".pdf",
    ".docx",
    ".xlsx",
    ".pptx",
    ".zip",
    ".tar",
    ".gz",
    ".lock",
]


def filter_by_extension(file, extensions):
    return any(file.endswith(ext) for ext in extensions)


class ReadPRs(Step):
    def __init__(self, inputs: DataPoint):
        super().__init__(inputs)
        missing_keys = ReadPRsInputs.__required_keys__.difference(inputs.keys())
        if len(missing_keys) > 0:
            raise ValueError(f"Missing required data: {missing_keys}")

        if "github_api_key" in inputs.keys():
            self.scm_client = GithubClient(inputs["github_api_key"])
        elif "gitlab_api_key" in inputs.keys():
            self.scm_client = GitlabClient(inputs["gitlab_api_key"])
        else:
            raise ValueError(f'Missing required input data: "github_api_key" or "gitlab_api_key"')

        if "scm_url" in inputs.keys():
            self.scm_client.set_url(inputs["scm_url"])

        self.repo_slug = inputs["repo_slug"]
        self.pr_ids = self.__parse_pr_ids_input(inputs.get("pr_ids"))
        self.pr_state = self.__parse_pr_state_input(inputs.get("pr_state"))

    @staticmethod
    def __parse_pr_ids_input(pr_ids_input: str | None) -> list:
        if not pr_ids_input:
            return []

        delimiter = None
        if "," in pr_ids_input:
            delimiter = ","
        return pr_ids_input.split(delimiter)

    @staticmethod
    def __parse_pr_state_input(state_input: str | None) -> PullRequestState:
        if not state_input:
            logger.debug(f"No pull request state given. Defaulting to OPEN.")
            return PullRequestState.OPEN

        state = getattr(PullRequestState, state_input.upper(), None)
        if state is None:
            logger.warning(f"Invalid pull request state: {state_input}. Defaulting to OPEN.")
            return PullRequestState.OPEN

        return state

    def run(self) -> List[DataPoint]:
        prs = self.scm_client.find_prs(self.repo_slug, state=self.pr_state)
        if len(prs) < 1:
            return list()

        if len(self.pr_ids) > 0:
            prs = filter(lambda _pr: str(_pr.id) in self.pr_ids, prs)

        data_points = []
        for pr in prs:
            data_point = self.__pr_to_data_point(pr)
            data_points.append(data_point)
        return data_points

    @staticmethod
    def __pr_to_data_point(pr):
        pr_texts = pr.texts()
        title = pr_texts.get("title", "")
        body = pr_texts.get("body", "")
        comments = pr_texts.get("comments", [])
        diffs = []
        for path, diff in pr_texts.get("diffs", {}).items():
            if filter_by_extension(path, _IGNORED_EXTENSIONS):
                continue
            diffs.append(dict(path=path, diff=diff))

        return dict(
            title=title,
            body=body,
            diffs=diffs,
            comments=comments,
        )
