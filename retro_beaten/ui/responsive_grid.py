"""Responsive cover layout with centered rows."""


def enable_responsive_grid(parent, covers):
    """Adapt columns and center each row of covers in the panel."""
    if not covers:
        return

    # Center the grid horizontally and align it to the top.
    parent.grid_anchor("n")

    # Share a temporary cell until the panel width is known.
    # A temporary column with hundreds of rows creates an oversized panel
    # that can displace images within their borders on Windows.
    # Each cover spans two small columns, allowing half-cell offsets.
    for cover_label in covers:
        cover_label.grid(row=0, column=0, columnspan=2, padx=10, pady=10)

    current_layout = None
    configured_columns = 0
    pending_layout = None

    def update_layout():
        nonlocal current_layout, configured_columns, pending_layout
        pending_layout = None

        # Measure frames and margins independently of their grid positions.
        # These measurements already include CustomTkinter scaling.
        cell_width = max(
            cover.winfo_reqwidth() + 2 * int(cover.grid_info()["padx"])
            for cover in covers
        )
        available_width = parent.winfo_width()
        if cell_width <= 0 or available_width <= 1:
            return

        half_cell_width = (cell_width + 1) // 2
        columns = max(1, min(len(covers), available_width // (2 * half_cell_width)))
        layout = (columns, half_cell_width)
        if layout == current_layout:
            return

        # Clear old widths when the column count decreases.
        for column in range(configured_columns):
            parent.grid_columnconfigure(column, minsize=0, weight=0)
        for column in range(columns * 2):
            parent.grid_columnconfigure(column, minsize=half_cell_width, weight=0)

        current_layout = layout
        configured_columns = columns * 2

        for index, cover_label in enumerate(covers):
            row = index // columns
            row_count = min(columns, len(covers) - row * columns)
            offset = columns - row_count
            cover_label.grid(
                row=row,
                column=offset + 2 * (index % columns),
                columnspan=2,
                padx=10,
                pady=10
            )

    def cancel_layout(event=None):
        nonlocal pending_layout
        if event is not None and event.widget is not parent:
            return
        if pending_layout is not None:
            parent.after_cancel(pending_layout)
            pending_layout = None

    def schedule_layout(event=None):
        nonlocal pending_layout
        # Wait for the width to settle before laying out the covers.
        cancel_layout()
        pending_layout = parent.after(50, update_layout)

    parent.bind("<Configure>", schedule_layout, add="+")
    parent.bind("<Destroy>", cancel_layout, add="+")
    schedule_layout()
