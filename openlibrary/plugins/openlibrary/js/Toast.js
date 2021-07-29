import $ from 'jquery';

/**
 * @constant {number} Default amount of time to display a toast component, in milliseconds.
 */
const DEFAULT_TIMEOUT = 2500;

/**
 * @class Toast creates a small pop-up message that closes after some amount of time.
 */
export class Toast {
  static $toastContainer;

  /**
   * Creates a new toast component, adds a close listener to the component, and adds the component
   * as the first child of the given parent element.
   *
   * @param {JQuery} $parent Designates where the toast component will be attached
   * @param {string} message Message that will be displayed in the toast component
   * @param {number} timeout Amount of time, in milliseconds, that the component will be visible
   */
  constructor($parent, message, timeout=DEFAULT_TIMEOUT) {
      if (!Toast.$toastContainer) {
          Toast.$toastContainer = $('<div class="toast-container"></div>');
      }
      if ($parent.has(Toast.$toastContainer).length === 0) {
          $parent.prepend(Toast.$toastContainer);
      }

      this.timeout = timeout;
      this.$toast = $(`<div class="toast">
        <span class="toast-message">${message}</span>
        <a class="toast--close">&times;<span class="shift">$_("Close")</span></a>
      </div>
    `);

      this.$toast.find('.toast--close').on('click', () => {
          this.close();
      });

      Toast.$toastContainer.append(this.$toast);
  }

  /**
   * Displays the toast component on the page.
   */
  show() {
      this.$toast.addClass('show');

      setTimeout(() => {
          this.close();
      }, this.timeout);
  }

  /**
   * Hides the toast component and removes it from the DOM.
   */
  close() {
      this.$toast.fadeOut('slow', function() { $(this).remove() });
  }
}
