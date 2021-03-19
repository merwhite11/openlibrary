import '../../../../../static/css/components/metadata-form.less';

export function initPatronMetadata() {
    function displayModal() {
        $.colorbox({
            inline: true,
            opacity: '0.5',
            href: '#metadata-form',
            width: '60%',
        });
    }

    function populateForm($form, observations) {
        let i18nStrings = JSON.parse(document.querySelector('#modal-link').dataset.i18n);

        for (const observation of observations) {
            let className = observation.multi_choice ? 'multi-choice' : 'single-choice';
            let $choices = $(`<div class="${className}"></div>`);
            let choiceIndex = observation.values.length;

            for (const value of observation.values) {
                let choiceId = `${observation.label}Choice${choiceIndex--}`;

                $choices.append(`
                <label for="${choiceId}" class="${className}-label">
                            <input type=${observation.multi_choice ? 'checkbox': 'radio'} name="${observation.label}" id="${choiceId}" value="${value}">
                            ${value}
                        </label>`);
            }

            $form.append(`
              <details class="aspect-section">
                <summary>${observation.label}</summary>
                <div id="${observation.label}-question">
                    <h3>${observation.description}</h3>
                    ${$choices.prop('outerHTML')}
                </div>
              </details>
            `);
        }

        $form.append(`
            <div class="formElement metadata-submit">
              <div class="form-buttons">
                <a class="small dialog--close plain" href="javascript:;" id="cancel-submission">${i18nStrings.close_text}</a>
                <input class="cta-btn submit-btn" type="submit" value="${i18nStrings.submit_text}">
              </div>
            </div>`);

        addToggleListeners($('.aspect-section', $form));
    }

    $('#modal-link').on('click', function() {
        if ($('#user-metadata').children().length === 0) {
            $.ajax({
                type: 'GET',
                url: '/observations',
                dataType: 'json'
            })
                .done(function(data) {
                    populateForm($('#user-metadata'), data.observations);
                    $('#cancel-submission').click(function() {
                        $.colorbox.close();
                    })
                    displayModal();
                })
                .fail(function() {
                    // TODO: Handle failed API calls gracefully.
                })
        } else {
            displayModal();
        }
    });

    $('#user-metadata').on('submit', function(event) {
        event.preventDefault();

        let context = JSON.parse(document.querySelector('#modal-link').dataset.context);
        let result = {};

        result['username'] = context.username;
        result['work_id'] = context.work.split('/')[2];

        if (context.edition) {
            result['edition_id'] = context.edition.split('/')[2];
        }

        result['observations'] = [];

        $(this).find('input[type=radio]:checked').each(function() {
            let currentPair = {};
            currentPair[$(this).attr('name')] = $(this).val()
            result['observations'].push(currentPair);
        })

        $(this).find('input[type=checkbox]:checked').each(function() {
            let currentPair = {};
            currentPair[$(this).attr('name')] = $(this).val()
            result['observations'].push(currentPair);
        })

        if (result['observations'].length > 0) {
            $.ajax({
                type: 'POST',
                url: '/observations',
                contentType: 'application/json',
                data: JSON.stringify(result)
            });
            $.colorbox.close();
        } else {
            // TODO: Handle case where no data was submitted
        }
    });
}

/**
 * Resizes modal when a details element is opened or closed.
 */
function toggleHandler() {
    let formHeight = $('#metadata-form').height();

    $('#cboxContent').height(formHeight + 22);
    $('#cboxLoadedContent').height(formHeight);
}

/**
 * Adds a toggle handler to all details elements.
 *
 * @param {JQuery} $toggleElements`Elements that will receive toggle handlers.
 */
function addToggleListeners($toggleElements) {
    $toggleElements.each(function() {
        $(this).on('toggle', toggleHandler);
    })
}
