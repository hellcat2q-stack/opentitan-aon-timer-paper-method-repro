"""Run the six-test pool with the existing V30 smoke, full, and audit workflow."""
import run_stage09_matrix_v30 as matrix


def configure():
    matrix.WORK_NAME = "stage09_6test_ablation_20261123"
    matrix.RUN_PREFIX = "stage09_6test"
    matrix.RUN_DATE = "20261123"
    matrix.SELECTED_TEST_COUNT = 6
    matrix.CATALOG_PATH = "configs/aon_timer_6test_catalog.json"
    matrix.POOL_LABEL = "六测试池"


if __name__ == "__main__":
    configure()
    matrix.main()
