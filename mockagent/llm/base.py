from abc import ABC, abstractmethod

from mockagent.schemas.field import FieldSpec, SampleProfile


class LLMFieldParser(ABC):
    @abstractmethod
    def parse_fields(
        self,
        profile: SampleProfile,
        target_columns: list[str] | None = None,
    ) -> list[FieldSpec]:
        raise NotImplementedError

    def parse_uncertain_fields(
        self,
        profile: SampleProfile,
        target_columns: list[str] | None = None,
    ) -> list[FieldSpec]:
        return self.parse_fields(profile, target_columns)
