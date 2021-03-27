/* Global constants */
const DEFAULT_LENGTH_MENU = [[10, 25, 50, 100 -1], [10, 25, 50, 100, "All"]]
const DEFAULT_PAGE_LENGTH = 50

/* Global functions */
// Remove the formatting to get integer data for summation
var intVal = function (i) {
    return typeof i === 'string' ?
        i.replace(/[\$,]/g, '') * 1 :
        typeof i === 'number' ?
            i : 0;
};
