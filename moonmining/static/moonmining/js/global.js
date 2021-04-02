/* Global constants */
const DEFAULT_LENGTH_MENU = [[10, 25, 50, 100 -1], [10, 25, 50, 100, "All"]]
const DEFAULT_PAGE_LENGTH = 50
const VALUE_DIVIDER = 1000000000

/* Global functions */
// Remove the formatting to get integer data for summation
var intVal = function (i) {
    return typeof i === 'string' ?
        i.replace(/[\$,]/g, '') * 1 :
        typeof i === 'number' ?
            i : 0;
};

// Format ISK values for output
function formatisk(data) {
    if ( data != null ) {
        return (data / VALUE_DIVIDER).toLocaleString(
            'en-US', {minimumFractionDigits: 1, maximumFractionDigits: 1}
        );
    }
    else {
        return "";
    }
}

// DataTables renderer for ISK values
$.fn.dataTable.render.formatisk = function () {
    return function ( data, type, row ) {
        if ( type === 'display' ) {
            return formatisk(data);
        }

        // Search, order and type can use the original data
        return data;
    };
};

// wrap boiler plate code for handling modal events
function handle_modal_events(modalId, modalContentId) {
    $('#' + modalId ).on('show.bs.modal', function (event) {
        var button = $(event.relatedTarget)
        var ajax_url = button.data('ajax_url');
        $('#' + modalContentId).load(ajax_url)
    });
}
