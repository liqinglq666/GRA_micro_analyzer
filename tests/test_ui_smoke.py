from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def test_main_window_constructs_after_refactor():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    assert window._tabs.count() == 5
    assert window._tabs.tabText(0) == "Data"
    assert window._tabs.tabText(1) == "GRG ranking"
    assert window._action_save.isEnabled() is False
    assert window._btn_save_grg_fig.isEnabled() is False
    assert window._btn_save_radar_fig.isEnabled() is False

    window.close()
    window.deleteLater()
    app.processEvents()
