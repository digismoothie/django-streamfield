(function ($) {
  window.ListBlock = function (opts) {
    /* contents of 'opts':
            definitionPrefix (required)
            childInitializer (optional) - JS initializer function for each child
        */
    var listMemberTemplate = $(
      '#' + opts.definitionPrefix + '-newmember',
    ).text();

    return function (elementPrefix) {
      var sequence = django.Sequence({
        prefix: elementPrefix,
        onInitializeMember: function (sequenceMember) {
          /* initialize child block's JS behaviour */
          if (opts.childInitializer) {
            opts.childInitializer(sequenceMember.prefix + '-value');
          }

          /* initialise delete button */
          $('#' + sequenceMember.prefix + '-delete').on('click', function () {
            sequenceMember.delete();
          });

          /* initialise move up/down buttons */
          $('#' + sequenceMember.prefix + '-moveup').on('click', function () {
            sequenceMember.moveUp();
          });

          $('#' + sequenceMember.prefix + '-movedown').on('click', function () {
            sequenceMember.moveDown();
          });
        },

        onEnableMoveUp: function (sequenceMember) {
          $('#' + sequenceMember.prefix + '-moveup').removeClass('disabled');
        },

        onDisableMoveUp: function (sequenceMember) {
          $('#' + sequenceMember.prefix + '-moveup').addClass('disabled');
        },

        onEnableMoveDown: function (sequenceMember) {
          $('#' + sequenceMember.prefix + '-movedown').removeClass('disabled');
        },

        onDisableMoveDown: function (sequenceMember) {
          $('#' + sequenceMember.prefix + '-movedown').addClass('disabled');
        },
      });

      /* initialize 'add' button */
      $('#' + elementPrefix + '-add').on('click', function () {
        sequence.insertMemberAtEnd(listMemberTemplate);
      });
    };
  };
})(django.jQuery);
