const getIsbnToElementMap = container => {
    const reISBN = /((978)?[0-9][0-9]{10}[0-9xX])|((978)?[0-9]{9}[0-9Xx])/;
    const elements = document.getElementsByClassName(container);
    let isbnElementMap = {};
    for (let i = 0; i < elements.length; i++) {
        let e = elements.item(i);
        let match = e.innerHTML.match(reISBN);
        if (match) {
            isbnElementMap[match[0]] = e;
        }
    }
    return isbnElementMap;
};

export const getAvailabilityDataFromArchiveOrg = async isbnList => {
    const apiUrl = 'https://archive.org/services/availability'
    const url = `${apiUrl}?isbn=${isbnList.join(',')}`;
    const response = await fetch(url);
    const jsonResponse = await response.json();
    return jsonResponse.responses;
};

export const addOpenLibraryButtons = async options => {
    const {bookContainer, btnParent} = options
    if (bookContainer === undefined || btnParent === undefined) {
        throw Error(
            'book container and button parent must be specified in options for open library buttons to populate!'
        )
    }
    const foundIsbnElementsMap = getIsbnToElementMap(bookContainer);
    const results = await getAvailabilityDataFromArchiveOrg(Object.keys(foundIsbnElementsMap))
    Object.keys(foundIsbnElementsMap).map((isbn) => {
        const availability = results[isbn];
        if (availability && availability.status !== 'error') {
            let e = foundIsbnElementsMap[isbn];
            let buttons = e.getElementsByClassName(btnParent)[0];
            buttons.innerHTML = `${buttons.innerHTML}<div><a class="openlibrary-btn" href="https://openlibrary.org/borrow/ia/${availability.identifier}?ref=">Open Library</a></div>`;
        }
    })
};
